"""
04_collect_lyrics.py — Coleta letras para as músicas que ainda não têm no banco.

Fontes (em ordem de prioridade):
    1. Vagalume API  (precisa de API key: https://auth.vagalume.com.br)
    2. Letras.mus.br (scraping — sem API key)

Pré-requisitos:
    pip install requests beautifulsoup4 rapidfuzz

Uso:
    # Definir a API key do Vagalume:
    export VAGALUME_API_KEY='sua_api_key'

    # Coletar letras para todas as músicas sem letra:
    python 04_collect_lyrics.py

    # Coletar para um gênero específico:
    python 04_collect_lyrics.py --genre brega_funk

    # Limitar o número de músicas (para teste):
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

# DB_PATH = os.path.join(os.path.dirname(__file__), "dataset.db")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "dataset.db")

try:
    import requests
    from bs4 import BeautifulSoup
    from rapidfuzz import fuzz
except ImportError:
    print("Erro: instale as dependências com:")
    print("  pip install requests beautifulsoup4 rapidfuzz")
    sys.exit(1)


def normalize_text(text):
    """Remove acentos, lowercase, e caracteres não alfanuméricos."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


# ══════════════════════════════════════════════════════════════
#  FONTE 1: Vagalume API
# ══════════════════════════════════════════════════════════════
def fetch_vagalume(artist_name, song_title, api_key):
    """Busca letra no Vagalume. Retorna (text, match_score) ou (None, 0)."""
    url = "https://api.vagalume.com.br/search.php"
    params = {
        "art":    artist_name,
        "mus":    song_title,
        "apikey": api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
    except Exception:
        return None, 0.0

    if data.get("type") != "exact" and data.get("type") != "aprox":
        return None, 0.0

    mus = data.get("mus")
    if not mus or len(mus) == 0:
        return None, 0.0

    text = mus[0].get("text", "")
    if not text:
        return None, 0.0

    # Calcular score de matching
    found_title = mus[0].get("name", "")
    score = fuzz.token_sort_ratio(normalize_text(song_title), normalize_text(found_title)) / 100
    return text, score


# ══════════════════════════════════════════════════════════════
#  FONTE 2: Letras.mus.br (scraping)
# ══════════════════════════════════════════════════════════════
def slugify(text):
    """Converte 'Chico Science' → 'chico-science'."""
    text = normalize_text(text)
    return re.sub(r"\s+", "-", text)


def fetch_letras(artist_name, song_title):
    """Busca letra no Letras.mus.br via scraping. Retorna (text, match_score) ou (None, 0)."""
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

    # Letras.mus.br usa a classe 'lyric-original' ou div com data de letras
    lyric_div = soup.find("div", class_="lyric-original")
    if not lyric_div:
        lyric_div = soup.find("div", class_="cnt-letra")
    if not lyric_div:
        return None, 0.0

    # Extrair texto preservando quebras de linha
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

    # Verificar se o título na página confere
    title_tag = soup.find("h1")
    page_title = title_tag.get_text().strip() if title_tag else ""
    score = fuzz.token_sort_ratio(normalize_text(song_title), normalize_text(page_title)) / 100

    return text, max(score, 0.7)  # se chegou na URL certa, score mínimo é 0.7


# ══════════════════════════════════════════════════════════════
#  ORQUESTRADOR
# ══════════════════════════════════════════════════════════════
def collect_lyrics_for_song(artist_name, song_title, vagalume_key):
    """Tenta coletar a letra de múltiplas fontes."""

    # Tentar Vagalume primeiro (se tiver API key)
    if vagalume_key:
        text, score = fetch_vagalume(artist_name, song_title, vagalume_key)
        if text and score >= 0.6:
            return text, "vagalume", score

    # Fallback: Letras.mus.br
    text, score = fetch_letras(artist_name, song_title)
    if text and score >= 0.6:
        return text, "letras", score

    return None, None, 0.0


def main():
    parser = argparse.ArgumentParser(description="Coleta letras de músicas")
    parser.add_argument("--genre", help="Filtrar por gênero", default=None)
    parser.add_argument("--limit", type=int, help="Limitar número de músicas", default=None)
    parser.add_argument("--min-score", type=float, help="Score mínimo de matching", default=0.6)
    args = parser.parse_args()

    vagalume_key = os.environ.get("VAGALUME_API_KEY", "")
    if not vagalume_key:
        print("⚠ VAGALUME_API_KEY não definida — usando apenas Letras.mus.br")

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Buscar músicas sem letra
    query = """
        SELECT s.song_id, s.title, a.name
        FROM songs s
        JOIN artists a ON s.artist_id = a.artist_id
        LEFT JOIN lyrics l ON s.song_id = l.song_id
        WHERE l.text IS NULL
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
    print(f"Músicas sem letra: {len(pending)}")

    n_found   = 0
    n_failed  = 0

    for i, (song_id, title, artist_name) in enumerate(pending, 1):
        print(f"  [{i}/{len(pending)}] {artist_name} — {title}", end="  ")

        text, source, score = collect_lyrics_for_song(artist_name, title, vagalume_key)

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
            # Inserir registro sem texto para não tentar de novo
            cur.execute(
                "INSERT OR IGNORE INTO lyrics (song_id, source, match_score) VALUES (?,?,?)",
                (song_id, "not_found", 0.0)
            )
            conn.commit()
            n_failed += 1
            print("✗ não encontrada")

        time.sleep(1.0)  # Rate limiting (respeitar os servidores)

    # Resumo
    progress = cur.execute("SELECT * FROM v_progress").fetchall()
    conn.close()

    print(f"\n{'═'*50}")
    print(f"Encontradas: {n_found}  |  Não encontradas: {n_failed}")
    print(f"\nProgresso por gênero:")
    print(f"  {'Gênero':<15} {'Total':>6} {'C/ letra':>9} {'S/ letra':>9} {'%':>6}")
    print(f"  {'─'*46}")
    for genre, total, with_l, without_l, pct in progress:
        print(f"  {genre:<15} {total:>6} {with_l:>9} {without_l:>9} {pct:>5.1f}%")


if __name__ == "__main__":
    main()
