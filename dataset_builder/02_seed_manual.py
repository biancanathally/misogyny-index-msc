"""
02_seed_manual.py — Popula o banco com algumas músicas de exemplo para testar o pipeline.

Uso:
    python 02_seed_manual.py

Adiciona ~15 músicas de exemplo (brega-funk, brega, mangue beat) com letras curtas
para que você possa testar a exportação e o pipeline sem precisar da API do Spotify.
"""
import sqlite3
import os

# DB_PATH = os.path.join(os.path.dirname(__file__), "dataset.db")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "dataset.db")

# ── Dados de exemplo ─────────────────────────────────────────
# Cada tupla: (artist_id, name, gender, type, city)
SAMPLE_ARTISTS = [
    ("artist_mc_gw",       "MC GW",           "M",    "Solo", "Recife"),
    ("artist_mc_loma",     "MC Loma",          "F",    "Solo", "Recife"),
    ("artist_dj_arnaldo",  "DJ Arnaldo",       "M",    "Solo", "Olinda"),
    ("artist_csnm",        "Chico Science",    "M",    "Solo", "Recife"),
    ("artist_nz",          "Nação Zumbi",      "M",    "Group","Recife"),
    ("artist_mundo_livre", "Mundo Livre S/A",  "M",    "Group","Recife"),
    ("artist_reginaldo",   "Reginaldo Rossi",  "M",    "Solo", "Recife"),
    ("artist_michelle",    "Michelle Melo",    "F",    "Solo", "Recife"),
]

# Cada tupla: (song_id, title, artist_id, genre, year, popularity, explicit)
SAMPLE_SONGS = [
    # ── Brega-funk ───────────────────
    ("song_bf_001", "Fake Amor",        "artist_mc_loma",    "brega_funk", 2019, 72, True),
    ("song_bf_002", "Envolvimento",     "artist_mc_loma",    "brega_funk", 2018, 85, False),
    ("song_bf_003", "Ritmo Mexicano",   "artist_mc_gw",      "brega_funk", 2017, 68, True),
    ("song_bf_004", "Elas Gostam",      "artist_dj_arnaldo", "brega_funk", 2020, 55, True),
    ("song_bf_005", "Senta e Desce",    "artist_mc_gw",      "brega_funk", 2021, 60, True),

    # ── Brega ────────────────────────
    ("song_br_001", "Garçom",           "artist_reginaldo",  "brega", 1987, 78, False),
    ("song_br_002", "De Volta pro Aconchego","artist_reginaldo","brega",1986,80,False),
    ("song_br_003", "Em Plena Lua de Mel","artist_reginaldo","brega", 1984, 65, False),
    ("song_br_004", "Recife Minha Cidade","artist_michelle",  "brega", 2005, 45, False),
    ("song_br_005", "Mon Amour",         "artist_michelle",  "brega", 2003, 50, False),

    # ── Mangue beat ──────────────────
    ("song_mb_001", "Da Lama ao Caos",     "artist_csnm",       "mangue_beat", 1994, 70, False),
    ("song_mb_002", "A Cidade",            "artist_csnm",       "mangue_beat", 1994, 75, False),
    ("song_mb_003", "Maracatu Atômico",    "artist_csnm",       "mangue_beat", 1996, 72, False),
    ("song_mb_004", "Quando a Maré Encher","artist_nz",         "mangue_beat", 2000, 45, False),
    ("song_mb_005", "Livre Iniciativa",    "artist_mundo_livre", "mangue_beat", 1998, 40, False),
]

# Letras de exemplo (fictícias / resumidas para teste — substitua pelas reais)
SAMPLE_LYRICS = [
    ("song_bf_001", """Fake amor, fake amor
Você disse que me amava mas era fake amor
Postou foto com outro e disse que era amigo
Agora tá querendo voltar pro meu abrigo
Mas eu não sou bobo não, não sou otário
Seu amor é falso, tá no dicionário
Fake amor, fake amor
Você só quer biscoito no Instagram""", "manual"),

    ("song_bf_002", """Envolvimento, envolvimento
Ela quer envolvimento
No baile ela desce até o chão
Envolvimento, envolvimento
Faz a fila e pega a senha
Que hoje tem diversão""", "manual"),

    ("song_mb_001", """Da lama ao caos, do caos à lama
Um homem roubado nunca se engana
O sol de Pernambuco nasce temperado
Com um pouco de dendê e muito suor no rosto
Faca de ponta, chapéu de couro
Na terra do maracatu
A cultura popular é a nossa identidade
Na ponte, no mangue, na cidade""", "manual"),

    ("song_mb_002", """A cidade se apresenta centro das ambições
Para mendigos ou reis
O sol nasce e ilumina as pedras evoluídas
Que cresceram com a força de pedreiros suados
A cidade não para, a cidade só cresce
O de cima sobe e o de baixo desce
A cidade se encontra prostituída
Por aqueles que a usaram em busca de diversão""", "manual"),

    ("song_br_001", """Garçom, aqui nesta mesa de bar
Você já cansou de escutar centenas de casos de amor
Garçom, no meu copo você pode ver
Que o mundo inteiro se resume nela
Que tudo mais não tem valor
Garçom, o meu coração tá pedindo
Um litro de pranto pra matar a saudade que traz""", "manual"),

    ("song_br_002", """De volta pro aconchego
De volta pro meu canto
De volta pro sossego
De volta pro meu pranto
Que bom poder estar aqui
De volta pro começo
De volta ao meu lugar""", "manual"),
]


def seed():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Inserir artistas
    n_artists = 0
    for a in SAMPLE_ARTISTS:
        try:
            cur.execute(
                "INSERT INTO artists (artist_id, name, gender, type, city) VALUES (?,?,?,?,?)", a
            )
            n_artists += 1
        except sqlite3.IntegrityError:
            pass  # já existe

    # Inserir músicas
    n_songs = 0
    for s in SAMPLE_SONGS:
        try:
            cur.execute(
                "INSERT INTO songs (song_id, title, artist_id, genre, year, spotify_popularity, explicit) "
                "VALUES (?,?,?,?,?,?,?)", s
            )
            n_songs += 1
        except sqlite3.IntegrityError:
            pass

    # Inserir letras
    n_lyrics = 0
    for song_id, text, source in SAMPLE_LYRICS:
        lines = [l for l in text.strip().split("\n") if l.strip()]
        words = text.split()
        try:
            cur.execute(
                "INSERT INTO lyrics (song_id, text, source, n_words, n_lines, match_score) "
                "VALUES (?,?,?,?,?,?)",
                (song_id, text.strip(), source, len(words), len(lines), 1.0)
            )
            n_lyrics += 1
        except sqlite3.IntegrityError:
            pass

    conn.commit()

    # Progresso
    progress = cur.execute("SELECT * FROM v_progress").fetchall()
    ready    = cur.execute("SELECT COUNT(*) FROM v_ready").fetchone()[0]

    conn.close()

    print(f"✓ Inseridos: {n_artists} artistas, {n_songs} músicas, {n_lyrics} letras")
    print(f"\nProgresso por gênero:")
    print(f"  {'Gênero':<15} {'Total':>6} {'C/ letra':>9} {'S/ letra':>9} {'%':>6}")
    print(f"  {'─'*46}")
    for genre, total, with_l, without_l, pct in progress:
        print(f"  {genre:<15} {total:>6} {with_l:>9} {without_l:>9} {pct:>5.1f}%")
    print(f"\n  Músicas prontas para o pipeline (v_ready): {ready}")


if __name__ == "__main__":
    seed()
