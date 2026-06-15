"""
01_setup_db.py — Cria o banco SQLite com a modelagem do dataset.

Uso:
    python 01_setup_db.py

Gera:
    dataset.db  (SQLite, ~4 KB vazio)
"""
import sqlite3
import os

# DB_PATH = os.path.join(os.path.dirname(__file__), "/data/raw/dataset.db")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "dataset.db")

SCHEMA = """
-- ════════════════════════════════════════════════════════════
--  ARTISTAS
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS artists (
    artist_id       TEXT PRIMARY KEY,          -- Spotify artist ID (ex: "4dpARuHxo51G3z768sgnrY")
    name            TEXT NOT NULL,
    gender          TEXT CHECK(gender IN ('M','F','Mixed','Unknown')) DEFAULT 'Unknown',
    type            TEXT CHECK(type IN ('Solo','Group')) DEFAULT 'Solo',
    city            TEXT,                      -- cidade de origem
    state           TEXT DEFAULT 'PE',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════
--  MÚSICAS
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS songs (
    song_id             TEXT PRIMARY KEY,      -- Spotify track ID
    title               TEXT NOT NULL,
    artist_id           TEXT NOT NULL,
    genre               TEXT NOT NULL CHECK(genre IN ('brega_funk','brega','mangue_beat','outro')),
    year                INTEGER,
    album_name          TEXT,
    spotify_popularity  INTEGER DEFAULT 0,     -- 0-100, atualizado periodicamente
    duration_ms         INTEGER,
    explicit            BOOLEAN DEFAULT 0,
    spotify_url         TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (artist_id) REFERENCES artists(artist_id)
);

-- ════════════════════════════════════════════════════════════
--  LETRAS
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS lyrics (
    song_id         TEXT PRIMARY KEY,
    text            TEXT,                      -- letra completa (pode ser NULL se ainda não coletada)
    source          TEXT CHECK(source IN ('vagalume','letras','genius','manual')),
    language        TEXT DEFAULT 'pt',
    n_words         INTEGER,
    n_lines         INTEGER,
    match_score     REAL,                      -- confiança do matching (0-1)
    collected_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (song_id) REFERENCES songs(song_id)
);

-- ════════════════════════════════════════════════════════════
--  PLAYLISTS DE ORIGEM (rastreabilidade)
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS playlist_sources (
    playlist_id     TEXT,
    playlist_name   TEXT,
    genre           TEXT,
    song_id         TEXT,
    added_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (playlist_id, song_id),
    FOREIGN KEY (song_id) REFERENCES songs(song_id)
);

-- ════════════════════════════════════════════════════════════
--  VIEWS ÚTEIS
-- ════════════════════════════════════════════════════════════

-- View principal: músicas com letra disponível (pronta para o pipeline)
CREATE VIEW IF NOT EXISTS v_ready AS
SELECT
    s.song_id,
    s.title,
    a.name        AS artist_name,
    a.artist_id,
    a.gender      AS artist_gender,
    a.type        AS artist_type,
    s.genre,
    s.year,
    s.year / 10 * 10 AS decade,
    s.spotify_popularity,
    s.explicit,
    l.text        AS lyrics,
    l.language,
    l.n_words,
    l.n_lines,
    l.source      AS lyrics_source
FROM songs s
JOIN artists a ON s.artist_id = a.artist_id
JOIN lyrics  l ON s.song_id   = l.song_id
WHERE l.text IS NOT NULL
  AND l.n_words >= 10
  AND l.n_lines >= 4;

-- View de progresso da coleta
CREATE VIEW IF NOT EXISTS v_progress AS
SELECT
    s.genre,
    COUNT(*)                                        AS total_songs,
    SUM(CASE WHEN l.text IS NOT NULL THEN 1 ELSE 0 END) AS with_lyrics,
    SUM(CASE WHEN l.text IS NULL     THEN 1 ELSE 0 END) AS missing_lyrics,
    ROUND(100.0 * SUM(CASE WHEN l.text IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_complete
FROM songs s
LEFT JOIN lyrics l ON s.song_id = l.song_id
GROUP BY s.genre;
"""

def setup():
    exists = os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()

    # Mostra tabelas criadas
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()

    conn.close()

    action = "Atualizado" if exists else "Criado"
    print(f"✓ {action}: {DB_PATH}")
    print(f"  Tabelas: {', '.join(t[0] for t in tables)}")

if __name__ == "__main__":
    setup()
