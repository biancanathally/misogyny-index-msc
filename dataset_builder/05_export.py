"""
05_export.py — Exporta o dataset do SQLite para os formatos do pipeline.

Formatos de saída:
    1. JSON Lines (.jsonl.gz)  — compatível com o pipeline da baseline
    2. CSV (.csv)              — para exploração rápida em planilhas
    3. JSON Lines por gênero   — um arquivo por gênero musical

Uso:
    # Exportar tudo:
    python 05_export.py

    # Exportar apenas CSV:
    python 05_export.py --format csv

    # Exportar para um diretório específico:
    python 05_export.py --outdir ../data/meu_dataset

    # Estatísticas do dataset sem exportar:
    python 05_export.py --stats
"""
import argparse
import sqlite3
import json
import gzip
import csv
import os
import sys
from datetime import datetime

# DB_PATH = os.path.join(os.path.dirname(__file__), "dataset.db")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "dataset.db")

FIELDS = [
    "song_id", "title", "artist_name", "artist_id", "artist_gender",
    "artist_type", "genre", "year", "decade", "spotify_popularity",
    "explicit", "lyrics", "language", "n_words", "n_lines", "lyrics_source"
]


def fetch_ready_songs(conn, genre=None):
    """Retorna todas as músicas prontas (com letra, ≥10 palavras, ≥4 linhas)."""
    query = "SELECT * FROM v_ready"
    params = []
    if genre:
        query += " WHERE genre = ?"
        params.append(genre)
    query += " ORDER BY genre, year, spotify_popularity DESC"

    cur = conn.execute(query, params)
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def export_jsonl(songs, filepath):
    """Exporta para JSON Lines compactado (.jsonl.gz)."""
    with gzip.open(filepath, "wt", encoding="utf-8") as f:
        for song in songs:
            f.write(json.dumps(song, ensure_ascii=False) + "\n")
    print(f"  ✓ {filepath} ({len(songs)} músicas, {os.path.getsize(filepath)/1024:.1f} KB)")


def export_csv(songs, filepath):
    """Exporta para CSV."""
    if not songs:
        print(f"  ✗ {filepath} — nenhuma música para exportar")
        return

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=songs[0].keys())
        writer.writeheader()
        for song in songs:
            # Truncar lyrics no CSV para não ficar enorme
            row = dict(song)
            if row.get("lyrics"):
                row["lyrics"] = row["lyrics"][:500] + "..." if len(row["lyrics"]) > 500 else row["lyrics"]
            writer.writerow(row)
    print(f"  ✓ {filepath} ({len(songs)} músicas, {os.path.getsize(filepath)/1024:.1f} KB)")


def export_jsonl_full(songs, filepath):
    """Exporta para JSON Lines sem compressão (para inspeção)."""
    with open(filepath, "w", encoding="utf-8") as f:
        for song in songs:
            f.write(json.dumps(song, ensure_ascii=False) + "\n")
    print(f"  ✓ {filepath} ({len(songs)} músicas, {os.path.getsize(filepath)/1024:.1f} KB)")


def show_stats(conn):
    """Mostra estatísticas detalhadas do dataset."""
    print("\n" + "═" * 60)
    print("  ESTATÍSTICAS DO DATASET")
    print("═" * 60)

    # Contagens gerais
    n_artists  = conn.execute("SELECT COUNT(*) FROM artists").fetchone()[0]
    n_songs    = conn.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
    n_lyrics   = conn.execute("SELECT COUNT(*) FROM lyrics WHERE text IS NOT NULL").fetchone()[0]
    n_ready    = conn.execute("SELECT COUNT(*) FROM v_ready").fetchone()[0]

    print(f"\n  Artistas:          {n_artists}")
    print(f"  Músicas:           {n_songs}")
    print(f"  Com letra:         {n_lyrics}")
    print(f"  Prontas (v_ready): {n_ready}")

    # Por gênero
    print(f"\n  {'Gênero':<15} {'Músicas':>8} {'C/ letra':>9} {'Prontas':>8} {'Pop. média':>10}")
    print(f"  {'─' * 52}")
    genres = conn.execute("""
        SELECT s.genre,
               COUNT(*)                                                 AS total,
               SUM(CASE WHEN l.text IS NOT NULL THEN 1 ELSE 0 END)     AS with_lyrics,
               SUM(CASE WHEN l.text IS NOT NULL AND l.n_words >= 10
                        AND l.n_lines >= 4 THEN 1 ELSE 0 END)          AS ready,
               ROUND(AVG(s.spotify_popularity), 1)                     AS avg_pop
        FROM songs s
        LEFT JOIN lyrics l ON s.song_id = l.song_id
        GROUP BY s.genre
    """).fetchall()
    for genre, total, with_l, ready, avg_pop in genres:
        print(f"  {genre:<15} {total:>8} {with_l:>9} {ready:>8} {avg_pop:>10}")

    # Por década
    ready_songs = fetch_ready_songs(conn)
    if ready_songs:
        decades = {}
        for s in ready_songs:
            d = s.get("decade", "?")
            decades[d] = decades.get(d, 0) + 1
        print(f"\n  Prontas por década:")
        for d in sorted(decades):
            print(f"    {d}s: {decades[d]}")

    # Fontes de letras
    sources = conn.execute("""
        SELECT source, COUNT(*) FROM lyrics
        WHERE text IS NOT NULL
        GROUP BY source
    """).fetchall()
    if sources:
        print(f"\n  Fontes de letras:")
        for src, count in sources:
            print(f"    {src}: {count}")

    # Top artistas
    top = conn.execute("""
        SELECT a.name, s.genre, COUNT(*) as n
        FROM songs s JOIN artists a ON s.artist_id = a.artist_id
        GROUP BY a.artist_id
        ORDER BY n DESC LIMIT 10
    """).fetchall()
    print(f"\n  Top 10 artistas por nº de músicas:")
    for name, genre, n in top:
        print(f"    {name} ({genre}): {n}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Exporta dataset para JSON/CSV")
    parser.add_argument("--outdir",  default="./export", help="Diretório de saída")
    parser.add_argument("--format",  choices=["all", "jsonl", "csv"], default="all")
    parser.add_argument("--stats",   action="store_true", help="Mostrar estatísticas sem exportar")
    parser.add_argument("--genre",   help="Exportar apenas um gênero")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)

    if args.stats:
        show_stats(conn)
        conn.close()
        return

    # Criar diretório de saída
    os.makedirs(args.outdir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d")

    songs = fetch_ready_songs(conn, genre=args.genre)
    if not songs:
        print("Nenhuma música pronta para exportar. Execute os scripts de coleta primeiro.")
        conn.close()
        return

    print(f"\nExportando {len(songs)} músicas para {args.outdir}/\n")

    # ── 1. Dataset completo ──────────────────────────────────
    if args.format in ("all", "jsonl"):
        export_jsonl(songs, os.path.join(args.outdir, f"lyrics_dataset_{timestamp}.jsonl.gz"))
        export_jsonl_full(songs, os.path.join(args.outdir, f"lyrics_dataset_{timestamp}.jsonl"))

    if args.format in ("all", "csv"):
        export_csv(songs, os.path.join(args.outdir, f"lyrics_dataset_{timestamp}.csv"))

    # ── 2. Um arquivo por gênero (formato mais próximo da baseline) ──
    if args.format in ("all", "jsonl") and not args.genre:
        genres = set(s["genre"] for s in songs)
        print(f"\n  Arquivos por gênero:")
        for genre in sorted(genres):
            genre_songs = [s for s in songs if s["genre"] == genre]
            export_jsonl(genre_songs,
                        os.path.join(args.outdir, f"lyrics_{genre}_{timestamp}.jsonl.gz"))

    # ── 3. Estatísticas ──────────────────────────────────────
    show_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
