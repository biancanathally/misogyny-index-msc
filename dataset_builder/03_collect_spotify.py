"""
03_collect_spotify.py — Coleta músicas e metadados do Spotify via API.

Pré-requisitos:
    pip install spotipy

    Crie um app em https://developer.spotify.com/dashboard
    e defina as variáveis de ambiente:
        export SPOTIPY_CLIENT_ID='seu_client_id'
        export SPOTIPY_CLIENT_SECRET='seu_client_secret'

Uso:
    # Coletar de uma playlist específica:
    python 03_collect_spotify.py --playlist "37i9dQZF1DX7nJFKMfHwvp" --genre brega_funk

    # Coletar de várias playlists listadas em um arquivo:
    python 03_collect_spotify.py --file playlists.txt

    # Formato do playlists.txt (uma por linha: playlist_id,genre):
    #   37i9dQZF1DX7nJFKMfHwvp,brega_funk
    #   37i9dQZF1DWXykhBFq3mok,brega
    #   5hNpAfsLx5953iZPRjqrtK,mangue_beat
"""
import argparse
import sqlite3
import os
import sys
import time

# DB_PATH = os.path.join(os.path.dirname(__file__), "dataset.db")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "dataset.db")

def get_spotify_client():
    """Inicializa o cliente Spotify com autenticação OAuth (obrigatória desde fev/2026)."""
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
    except ImportError:
        print("Erro: instale o spotipy com 'pip install spotipy'")
        sys.exit(1)

    client_id     = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    redirect_uri  = os.environ.get("SPOTIPY_REDIRECT_URI")

    if not client_id or not client_secret or not redirect_uri:
        print("Erro: defina as variáveis de ambiente:")
        print("  export SPOTIPY_CLIENT_ID='seu_client_id'")
        print("  export SPOTIPY_CLIENT_SECRET='seu_client_secret'")
        print("  export SPOTIPY_REDIRECT_URI='http://127.0.0.1:8000/callback'")
        sys.exit(1)

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="playlist-read-private"
    )
    return spotipy.Spotify(auth_manager=auth)


def collect_playlist(sp, playlist_id, genre, conn):
    """Coleta todas as faixas de uma playlist e insere no banco."""
    cur = conn.cursor()

    # Buscar nome da playlist
    try:
        playlist = sp.playlist(playlist_id, fields="name,owner.display_name")
        playlist_name = playlist.get("name", "Desconhecida")
    except Exception as e:
        print(f"  Erro ao acessar playlist {playlist_id}: {e}")
        return 0

    print(f"  Playlist: {playlist_name}")

    # Paginar faixas com sp.playlist_tracks (não depende do campo 'total')
    n_inserted = 0
    offset = 0

    while True:
        try:
            results = sp.playlist_tracks(playlist_id, offset=offset, limit=100)
        except Exception as e:
            print(f"  Erro ao buscar faixas (offset={offset}): {e}")
            break

        items = results.get("items", [])
        if not items:
            break

        for item in items:
            # API pré-2026 usa "track", pós-2026 usa "item"
            track = item.get("track") or item.get("item")
            if not track or not track.get("id"):
                continue

            # Extrair dados do artista principal
            artists = track.get("artists", [])
            if not artists:
                continue
            artist = artists[0]
            artist_id   = artist.get("id", "")
            artist_name = artist.get("name", "Desconhecido")
            if not artist_id:
                continue

            # Inserir artista (se não existir)
            cur.execute(
                "INSERT OR IGNORE INTO artists (artist_id, name) VALUES (?, ?)",
                (artist_id, artist_name)
            )

            # Extrair dados da música
            song_id     = track["id"]
            title       = track["name"]
            album_name  = track.get("album", {}).get("name", "")
            year        = None
            release     = track.get("album", {}).get("release_date", "")
            if release and len(release) >= 4:
                try:
                    year = int(release[:4])
                except ValueError:
                    pass

            popularity  = track.get("popularity", 0)
            duration_ms = track.get("duration_ms", 0)
            explicit    = track.get("explicit", False)
            spotify_url = track.get("external_urls", {}).get("spotify", "")

            # Inserir música
            try:
                cur.execute(
                    """INSERT INTO songs
                       (song_id, title, artist_id, genre, year, album_name,
                        spotify_popularity, duration_ms, explicit, spotify_url)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (song_id, title, artist_id, genre, year, album_name,
                     popularity, duration_ms, explicit, spotify_url)
                )
                n_inserted += 1
            except sqlite3.IntegrityError:
                # Já existe — atualizar popularidade (pode ter mudado)
                cur.execute(
                    "UPDATE songs SET spotify_popularity = ? WHERE song_id = ?",
                    (popularity, song_id)
                )

            # Registrar origem (playlist → song)
            cur.execute(
                "INSERT OR IGNORE INTO playlist_sources (playlist_id, playlist_name, genre, song_id) "
                "VALUES (?,?,?,?)",
                (playlist_id, playlist_name, genre, song_id)
            )

        offset += len(items)
        # Se veio menos que 100, chegamos ao final
        if len(items) < 100:
            break
        time.sleep(0.2)  # Rate limiting

    conn.commit()
    return n_inserted


def main():
    parser = argparse.ArgumentParser(description="Coleta músicas do Spotify")
    parser.add_argument("--playlist", help="ID da playlist do Spotify")
    parser.add_argument("--genre",    help="Gênero: brega_funk, brega, mangue_beat, outro",
                        choices=["brega_funk", "brega", "mangue_beat", "outro"])
    parser.add_argument("--file",     help="Arquivo com lista de playlists (playlist_id,genre)")
    args = parser.parse_args()

    if not args.playlist and not args.file:
        parser.print_help()
        print("\nExemplo:")
        print("  python 03_collect_spotify.py --playlist 37i9dQZF1DX7nJFKMfHwvp --genre brega_funk")
        return

    sp   = get_spotify_client()
    conn = sqlite3.connect(DB_PATH)

    playlists = []
    if args.file:
        with open(args.file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(",")
                if len(parts) >= 2:
                    playlists.append((parts[0].strip(), parts[1].strip()))
    else:
        playlists.append((args.playlist, args.genre))

    total_inserted = 0
    for pid, genre in playlists:
        print(f"\n{'─'*50}")
        n = collect_playlist(sp, pid, genre, conn)
        print(f"  → {n} músicas novas inseridas")
        total_inserted += n

    # Mostrar progresso
    progress = conn.execute("SELECT * FROM v_progress").fetchall()
    conn.close()

    print(f"\n{'═'*50}")
    print(f"Total de músicas novas inseridas: {total_inserted}")
    print(f"\nProgresso por gênero:")
    print(f"  {'Gênero':<15} {'Total':>6} {'C/ letra':>9} {'S/ letra':>9} {'%':>6}")
    print(f"  {'─'*46}")
    for genre, total, with_l, without_l, pct in progress:
        print(f"  {genre:<15} {total:>6} {with_l:>9} {without_l:>9} {pct:>5.1f}%")


if __name__ == "__main__":
    main()
