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
    """Converte texto para slug de URL do Letras.mus.br."""
    # Trocar / por espaço ANTES de remover caracteres especiais
    text = text.replace("/", " ")
    text = normalize_text(text)
    text = re.sub(r"\s+", "-", text.strip())
    return text


def clean_title(title):
    """Remove sufixos, feats, parts e conteúdo entre parênteses/colchetes."""
    # Remover TUDO entre parênteses ou colchetes
    title = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", title)
    # Remover "- Ao Vivo", "- Remix", etc.
    title = re.sub(r"\s*[-–]\s*(Ao Vivo|Remix|Mix|Live|Remaster(ed)?|Bonus Track|Acústico|Acustico).*$", "", title, flags=re.IGNORECASE)
    # Remover feat/part/ft sem parênteses (ex: "Dally feat MC Biel")
    title = re.sub(r"\s*(feat\.?|ft\.?|part\.?|featuring|participação|com)\s.*$", "", title, flags=re.IGNORECASE)
    return title.strip()


def fetch_letras(artist_name, song_title):
    """Busca letra no Letras.mus.br via página do artista."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # 1. Encontrar a página do artista (tentar slugs progressivamente mais curtos)
    slug_parts = slugify(artist_name).split("-")
    artist_url = None

    for end in range(len(slug_parts), 0, -1):
        slug_try = "-".join(slug_parts[:end])
        url = f"https://www.letras.mus.br/{slug_try}/"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200 and f"/{slug_try}/" in resp.url:
                artist_url = url
                artist_slug = slug_try
                break
        except Exception:
            continue

    if not artist_url:
        return None, 0.0

    # 2. Buscar links de músicas na página do artista
    soup = BeautifulSoup(resp.text, "html.parser")
    song_links = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text().strip()
        if (
            href.startswith(f"/{artist_slug}/")
            and href != f"/{artist_slug}/"
            and text
            and not href.endswith(".html")
        ):
            song_links.append((href, text))

    if not song_links:
        return None, 0.0

    # 3. Encontrar a música mais parecida com o título buscado
    cleaned = clean_title(song_title)
    best_href = None
    best_score = 0

    for href, link_text in song_links:
        cleaned_link = clean_title(link_text)
        score1 = fuzz.token_sort_ratio(normalize_text(song_title), normalize_text(link_text)) / 100
        score2 = fuzz.token_sort_ratio(normalize_text(cleaned), normalize_text(link_text)) / 100
        score3 = fuzz.token_sort_ratio(normalize_text(cleaned), normalize_text(cleaned_link)) / 100
        score = max(score1, score2, score3)
        
        if score > best_score:
            best_score = score
            best_href = href

    if best_score < 0.5 or not best_href:
        return None, 0.0

    # 4. Acessar a página da letra
    song_url = f"https://www.letras.mus.br{best_href}"
    try:
        resp2 = requests.get(song_url, headers=headers, timeout=10)
        if resp2.status_code != 200:
            return None, 0.0
    except Exception:
        return None, 0.0

    soup2 = BeautifulSoup(resp2.text, "html.parser")

    lyric_div = soup2.find("div", class_="lyric-original")
    if not lyric_div:
        lyric_div = soup2.find("div", class_="cnt-letra")
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

    return text, best_score


# ==============================================================
#  ORQUESTRADOR
# ==============================================================
def collect_lyrics_for_song(artist_name, song_title):
    # 1. Letras.mus.br (principal)
    text, score = fetch_letras(artist_name, song_title)
    if text and score >= 0.6:
        return text, "letras", score

    return None, None, 0.0


def main():
    parser = argparse.ArgumentParser(description="Coleta letras de musicas")
    parser.add_argument("--genre", help="Filtrar por genero", default=None)
    parser.add_argument(
        "--limit", type=int, help="Limitar numero de musicas", default=None
    )
    parser.add_argument(
        "--min-score", type=float, help="Score minimo de matching", default=0.6
    )
    args = parser.parse_args()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

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

    n_found = 0
    n_failed = 0

    for i, (song_id, title, artist_name) in enumerate(pending, 1):
        print(f"  [{i}/{len(pending)}] {artist_name} — {title}", end="  ")

        text, source, score = collect_lyrics_for_song(artist_name, title)

        if text and score >= args.min_score and len(text.split()) <= 1500:
            lines = [l for l in text.strip().split("\n") if l.strip()]
            words = text.split()
            cur.execute(
                """INSERT OR REPLACE INTO lyrics
                   (song_id, text, source, n_words, n_lines, match_score)
                   VALUES (?,?,?,?,?,?)""",
                (song_id, text.strip(), source, len(words), len(lines), round(score, 3)),
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
    print(f"\nProgresso por gênero:")
    print(f"  {'Gênero':<15} {'Total':>6} {'C/ letra':>9} {'S/ letra':>9} {'%':>6}")
    print(f"  {'-'*46}")
    for genre, total, with_l, without_l, pct in progress:
        print(f"  {genre:<15} {total:>6} {with_l:>9} {without_l:>9} {pct:>5.1f}%")


if __name__ == "__main__":
    main()
