"""
04_collect_lyrics.py — Coleta letras para as músicas que ainda não têm no banco.

Fontes (em ordem de prioridade):
    1. Letras.mus.br  (scraping — sem API key)
    2. Genius API      (fallback — precisa de token)

Pré-requisitos:
    pip install requests beautifulsoup4 rapidfuzz lyricsgenius

Uso:
    python 04_collect_lyrics.py
    python 04_collect_lyrics.py --genre brega_funk
    python 04_collect_lyrics.py --limit 10
"""
import argparse
import sqlite3
import os
import sys
import time
import re
import unicodedata

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "dataset.db")

try:
    import requests
    from bs4 import BeautifulSoup
    from rapidfuzz import fuzz
except ImportError:
    print("Erro: pip install requests beautifulsoup4 rapidfuzz lyricsgenius")
    sys.exit(1)


def normalize_text(text):
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


# ==============================================================
#  FONTE 1: Letras.mus.br (principal)
# ==============================================================
def slugify(text):
    text = normalize_text(text)
    return re.sub(r"\s+", "-", text)


def fetch_letras(artist_name, song_title):
    slug_artist = slugify(artist_name)
    slug_song   = slugify(song_title)
    url = f"https://www.letras.mus.br/{slug_artist}/{slug_song}/"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None, 0.0
    except Exception:
        return None, 0.0

    soup = BeautifulSoup(resp.text, "html.parser")

    lyric_div = soup.find("div", class_="lyric-original")
    if not lyric_div:
        lyric_div = soup.find("div", class_="cnt-letra")
    if not lyric_div:
        return None, 0.0

    paragraphs = lyric_div.find_all("p")
    if paragraphs:
        lines = []
        for p in paragraphs:
            for br in p.find_all("br"):
                br.replace_with("\n")
            lines.append(p.get_text())
        text = "\n\n".join(lines)
    else:
        for br in lyric_div.find_all("br"):
            br.replace_with("\n")
        text = lyric_div.get_text()

    text = text.strip()
    if len(text) < 20:
        return None, 0.0

    title_tag = soup.find("h1")
    page_title = title_tag.get_text().strip() if title_tag else ""
    score = fuzz.token_sort_ratio(normalize_text(song_title), normalize_text(page_title)) / 100

    return text, max(score, 0.7)


# ==============================================================
#  FONTE 2: Genius (fallback)
# ==============================================================
_genius_client = None

def get_genius_client():
    global _genius_client
    if _genius_client is not None:
        return _genius_client

    token = os.environ.get("GENIUS_ACCESS_TOKEN", "")
    if not token:
        return None

    try:
        import lyricsgenius
        # _genius_client = lyricsgenius.Genius(
        #     token, verbose=False, timeout=15, retries=2,
        #     remove_section_headers=True,
        # )
        _genius_client = lyricsgenius.Genius(token)
        return _genius_client
    except ImportError:
        print("  lyricsgenius nao instalado — pip install lyricsgenius")
        return None


def fetch_genius(artist_name, song_title):
    genius = get_genius_client()
    if genius is None:
        return None, 0.0

    try:
        song = genius.search_song(song_title, artist_name)
    except Exception:
        return None, 0.0

    if not song or not song.lyrics:
        return None, 0.0

    text = song.lyrics.strip()
    lines = text.split("\n")
    if lines and lines[0].lower().endswith("lyrics"):
        lines = lines[1:]
    while lines and (re.match(r"^\d*Embed$", lines[-1].strip()) or lines[-1].strip() == ""):
        lines.pop()

    text = "\n".join(lines).strip()
    if len(text) < 20:
        return None, 0.0

    found_title = song.title if song.title else ""
    score = fuzz.token_sort_ratio(normalize_text(song_title), normalize_text(found_title)) / 100
    return text, max(score, 0.6)


# ==============================================================
#  ORQUESTRADOR
# ==============================================================
def collect_lyrics_for_song(artist_name, song_title):
    # 1. Letras.mus.br (principal)
    text, score = fetch_letras(artist_name, song_title)
    if text and score >= 0.6:
        return text, "letras", score

    # 2. Genius (fallback)
    text, score = fetch_genius(artist_name, song_title)
    if text and score >= 0.6:
        return text, "genius", score

    return None, None, 0.0


def main():
    parser = argparse.ArgumentParser(description="Coleta letras de musicas")
    parser.add_argument("--genre", help="Filtrar por genero", default=None)
    parser.add_argument("--limit", type=int, help="Limitar numero de musicas", default=None)
    parser.add_argument("--min-score", type=float, help="Score minimo de matching", default=0.6)
    args = parser.parse_args()

    genius_token = os.environ.get("GENIUS_ACCESS_TOKEN", "")
    if not genius_token:
        print("GENIUS_ACCESS_TOKEN nao definida — usando apenas Letras.mus.br")
    else:
        print("Genius configurado como fallback")

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    query = """
        SELECT s.song_id, s.title, a.name
        FROM songs s
        JOIN artists a ON s.artist_id = a.artist_id
        LEFT JOIN lyrics l ON s.song_id = l.song_id
        WHERE l.song_id IS NULL
    """
    params = []
    if args.genre:
        query += " AND s.genre = ?"
        params.append(args.genre)
    query += " ORDER BY s.spotify_popularity DESC"
    if args.limit:
        query += " LIMIT ?"
        params.append(args.limit)

    pending = cur.execute(query, params).fetchall()
    print(f"\nMusicas sem letra: {len(pending)}\n")

    n_found  = 0
    n_failed = 0

    for i, (song_id, title, artist_name) in enumerate(pending, 1):
        print(f"  [{i}/{len(pending)}] {artist_name} — {title}", end="  ")

        text, source, score = collect_lyrics_for_song(artist_name, title)

        if text and score >= args.min_score:
            lines = [l for l in text.strip().split("\n") if l.strip()]
            words = text.split()
            cur.execute(
                """INSERT OR REPLACE INTO lyrics
                   (song_id, text, source, n_words, n_lines, match_score)
                   VALUES (?,?,?,?,?,?)""",
                (song_id, text.strip(), source, len(words), len(lines), round(score, 3))
            )
            conn.commit()
            n_found += 1
            print(f"✓ {source} (score={score:.2f}, {len(words)} palavras)")

        else:
            n_failed += 1
            print("✗ não encontrada")


        time.sleep(1.5)

    progress = cur.execute("SELECT * FROM v_progress").fetchall()
    conn.close()

    print(f"\n{'='*50}")
    print(f"Encontradas: {n_found}  |  Nao encontradas: {n_failed}")
    print(f"\nProgresso por genero:")
    print(f"  {'Genero':<15} {'Total':>6} {'C/ letra':>9} {'S/ letra':>9} {'%':>6}")
    print(f"  {'-'*46}")
    for genre, total, with_l, without_l, pct in progress:
        print(f"  {genre:<15} {total:>6} {with_l:>9} {without_l:>9} {pct:>5.1f}%")


if __name__ == "__main__":
    main()
