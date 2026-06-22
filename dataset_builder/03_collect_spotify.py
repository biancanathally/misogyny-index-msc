"""
03_collect_spotify.py — Coleta musicas e metadados do Spotify via API.

Pre-requisitos:
    pip install spotipy python-dotenv
    Criar .env na raiz do projeto com as credenciais
    SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI e GENIUS_ACCESS_TOKEN (veja README.md)

Uso:
    # Por playlist (sua propria playlist):
    python 03_collect_spotify.py --playlist PLAYLIST_ID --genre brega_funk
    python 03_collect_spotify.py --file playlists.txt

    # Por artista (busca todas as faixas):
    python 03_collect_spotify.py --artist "MC Loma" --genre brega_funk
    python 03_collect_spotify.py --artists-file artists.txt

    # Formatos dos arquivos .txt:
    #   playlists.txt  ->  playlist_id,genre
    #   artists.txt    ->  nome do artista,genre
"""
import argparse
import sqlite3
import os
import sys
import time

# Carregar .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "dataset.db")


def get_spotify_client():
    """Inicializa o cliente Spotify com OAuth."""
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
    except ImportError:
        print("Erro: pip install spotipy")
        sys.exit(1)

    client_id     = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    redirect_uri  = os.environ.get("SPOTIPY_REDIRECT_URI")

    if not client_id or not client_secret or not redirect_uri:
        print("Erro: defina SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET e SPOTIPY_REDIRECT_URI")
        print("no arquivo .env ou como variaveis de ambiente.")
        sys.exit(1)

    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="playlist-read-private"
    ))


# ==============================================================
#  HELPER: inserir uma track no banco
# ==============================================================
def insert_track(cur, track, genre, source_type, source_id, source_name):
    """Insere uma track no banco. Retorna True se nova, False se ja existia."""
    if not track or not track.get("id"):
        return False

    artists = track.get("artists", [])
    if not artists:
        return False
    artist = artists[0]
    artist_id   = artist.get("id", "")
    artist_name = artist.get("name", "Desconhecido")
    if not artist_id:
        return False

    cur.execute("INSERT OR IGNORE INTO artists (artist_id, name) VALUES (?,?)",
                (artist_id, artist_name))

    song_id     = track["id"]
    title       = track.get("name", "")
    album_name  = track.get("album", {}).get("name", "")
    year        = None
    release     = track.get("album", {}).get("release_date", "")
    if release and len(release) >= 4:
        try:
            year = int(release[:4])
        except ValueError:
            pass

    popularity  = track.get("popularity", 0)  # pode ser 0 se a API nao retornar
    duration_ms = track.get("duration_ms", 0)
    explicit    = track.get("explicit", False)
    spotify_url = track.get("external_urls", {}).get("spotify", "")

    is_new = False
    try:
        cur.execute(
            """INSERT INTO songs
               (song_id, title, artist_id, genre, year, album_name,
                spotify_popularity, duration_ms, explicit, spotify_url)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (song_id, title, artist_id, genre, year, album_name,
             popularity, duration_ms, explicit, spotify_url)
        )
        is_new = True
    except sqlite3.IntegrityError:
        pass  # ja existe

    cur.execute(
        "INSERT OR IGNORE INTO playlist_sources (playlist_id, playlist_name, genre, song_id) "
        "VALUES (?,?,?,?)",
        (source_id, source_name, genre, song_id)
    )
    return is_new


# ==============================================================
#  MODO 1: Coleta por artista (via search)
# ==============================================================
def collect_artist(sp, artist_name, genre, conn):
    """Coleta a discografia completa de um artista via artist_albums."""
    cur = conn.cursor()
    print(f"  Buscando: {artist_name}")
    source_name = f"artist:{artist_name}"

    # 1. Encontrar o artista
    from rapidfuzz import fuzz
    try:
        r = sp.search(q=artist_name, type="artist", market="BR", limit=5)
    except Exception as e:
        print(f"  Erro na busca: {e}")
        return 0

    artists = r.get("artists", {}).get("items", [])
    if not artists:
        print(f"  Artista não encontrado")
        return 0

    best = max(artists, key=lambda a: fuzz.token_sort_ratio(
        artist_name.lower(), a.get("name", "").lower()
    ))
    
    artist_id = best["id"]
    found_name = best["name"]
    
    # Isso rejeita artistas quando o nome encontrado no Spotify difere muito
    score = fuzz.token_sort_ratio(artist_name.lower(), found_name.lower())
    if score < 80:
        print(f"  Ignorado: '{found_name}' (score={score}, muito diferente de '{artist_name}')")
        return 0
    
    print(f"  Encontrado: {found_name} (ID: {artist_id})")

    # 2. Buscar todos os álbuns (paginando com limit=10)
    album_ids = []
    offset = 0
    while True:
        try:
            result = sp.artist_albums(artist_id, album_type="album,single", limit=10, offset=offset)
        except Exception as e:
            print(f"  Erro ao buscar albums (offset={offset}): {e}")
            break

        items = result.get("items", [])
        if not items:
            break

        for album in items:
            aid = album.get("id")
            if aid:
                album_ids.append(aid)

        offset += len(items)
        if len(items) < 10:
            break
        time.sleep(0.5)

    print(f"  Albums/singles: {len(album_ids)}")

    # 3. Buscar faixas de cada álbum e inserir direto
    n_inserted = 0
    seen_ids = set()

    for album_id in album_ids:
        # Pegar info do álbum (nome e data) que já veio no passo 2
        try:
            album_info = sp.album(album_id)
        except Exception:
            album_info = {}

        album_name = album_info.get("name", "")
        release_date = album_info.get("release_date", "")

        # Buscar faixas do álbum
        try:
            result = sp.album_tracks(album_id, limit=10)
        except Exception:
            continue

        while True:
            for t in result.get("items", []):
                tid = t.get("id")
                if not tid or tid in seen_ids:
                    continue
                seen_ids.add(tid)

                # Montar objeto compatível com insert_track
                track = {
                    "id": tid,
                    "name": t.get("name", ""),
                    "artists": t.get("artists", []),
                    "album": {
                        "name": album_name,
                        "release_date": release_date,
                    },
                    "duration_ms": t.get("duration_ms", 0),
                    "explicit": t.get("explicit", False),
                    "external_urls": t.get("external_urls", {}),
                    "popularity": 0,
                }

                if insert_track(cur, track, genre, "artist_albums", artist_id, source_name):
                    n_inserted += 1

            # Paginar se tiver mais faixas
            if result.get("next"):
                try:
                    result = sp.next(result)
                except Exception:
                    break
            else:
                break

        time.sleep(0.5)

    conn.commit()
    print(f"  Faixas unicas: {len(seen_ids)} | Novas inseridas: {n_inserted}")
    return n_inserted


# ==============================================================
#  MODO 2: Coleta por playlist
# ==============================================================
def collect_playlist(sp, playlist_id, genre, conn):
    """Coleta faixas de uma playlist propria."""
    cur = conn.cursor()

    try:
        playlist = sp.playlist(playlist_id, fields="name")
        playlist_name = playlist.get("name", "Desconhecida")
    except Exception as e:
        print(f"  Erro ao acessar playlist {playlist_id}: {e}")
        return 0

    print(f"  Playlist: {playlist_name}")
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
            track = item.get("track") or item.get("item")
            if insert_track(cur, track, genre, "playlist", playlist_id, playlist_name):
                n_inserted += 1

        offset += len(items)
        if len(items) < 100:
            break
        time.sleep(2)

    conn.commit()
    return n_inserted


# def spotify_search_with_retry(sp, **kwargs):
#     """Faz busca no Spotify com retry automatico em caso de rate limit."""
#     import spotipy
#     for attempt in range(3):
#         try:
#             return sp.search(**kwargs)
#         except spotipy.exceptions.SpotifyException as e:
#             if e.http_status == 429:
#                 retry_after = int(e.headers.get("Retry-After", 30))
#                 print(f"\n  Rate limit - esperando {retry_after}s...", end="", flush=True)
#                 time.sleep(retry_after + 1)
#                 print(" retomando.", flush=True)
#             else:
#                 raise
#     return None


# ==============================================================
#  MAIN
# ==============================================================
def show_progress(conn):
    progress = conn.execute("SELECT * FROM v_progress").fetchall()
    print(f"\nProgresso por genero:")
    print(f"  {'Genero':<15} {'Total':>6} {'C/ letra':>9} {'S/ letra':>9} {'%':>6}")
    print(f"  {'-'*46}")
    for genre, total, with_l, without_l, pct in progress:
        print(f"  {genre:<15} {total:>6} {with_l:>9} {without_l:>9} {pct:>5.1f}%")


def main():
    parser = argparse.ArgumentParser(
        description="Coleta musicas do Spotify (por playlist ou por artista)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python 03_collect_spotify.py --playlist ID --genre brega_funk
  python 03_collect_spotify.py --file playlists.txt
  python 03_collect_spotify.py --artist "MC Loma" --genre brega_funk
  python 03_collect_spotify.py --artists-file artists.txt
        """
    )
    parser.add_argument("--playlist",     help="ID da playlist")
    parser.add_argument("--file",         help="Arquivo com playlists (id,genre)")
    parser.add_argument("--artist",       help="Nome do artista")
    parser.add_argument("--artists-file", help="Arquivo com artistas (nome,genre)")
    parser.add_argument("--genre",        help="Genero musical",
                        choices=["brega_funk", "brega", "manguebeat", "outro"])
    args = parser.parse_args()

    has_playlist = args.playlist or args.file
    has_artist   = args.artist or args.artists_file

    if not has_playlist and not has_artist:
        parser.print_help()
        return

    sp   = get_spotify_client()
    conn = sqlite3.connect(DB_PATH)
    total_inserted = 0

    # Modo playlist
    if has_playlist:
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
            if not args.genre:
                print("Erro: --genre e obrigatorio com --playlist")
                return
            playlists.append((args.playlist, args.genre))

        for pid, genre in playlists:
            print(f"\n{'-'*50}")
            n = collect_playlist(sp, pid, genre, conn)
            print(f"  -> {n} musicas novas")
            total_inserted += n

    # Modo artista
    if has_artist:
        artists_list = []
        if args.artists_file:
            with open(args.artists_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(",")
                    if len(parts) >= 2:
                        artists_list.append((parts[0].strip(), parts[1].strip()))
        else:
            if not args.genre:
                print("Erro: --genre e obrigatorio com --artist")
                return
            artists_list.append((args.artist, args.genre))

        for name, genre in artists_list:
            print(f"\n{'-'*50}")
            n = collect_artist(sp, name, genre, conn)
            total_inserted += n

    print(f"\n{'='*50}")
    print(f"Total de musicas novas: {total_inserted}")
    show_progress(conn)
    conn.close()


if __name__ == "__main__":
    main()
