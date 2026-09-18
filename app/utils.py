import re
import requests
import yaml
import os

STRING_CONFIG_KEYS = {
    "media-user-token",
    "authorization-token",
    "language",
    "storefront",
    "alac-save-folder",
    "atmos-save-folder",
    "aac-save-folder",
    "album-folder-format",
    "playlist-folder-format",
    "song-file-format",
    "artist-folder-format",
    "explicit-tag",
    "clean-tag",
    "master-tag",
    "convert-format",
    "ffmpeg-path",
    "ffmpeg-args",
}

BOOL_CONFIG_KEYS = {
    "use-song-info-for-playlist",
    "download-album-cover-for-playlist",
    "convert-after-download",
    "keep-original",
}

REQUIRED_CONFIG_KEYS = set(STRING_CONFIG_KEYS)

def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


MEDIA_CATEGORY_LABELS = {
    "album": "Álbum",
    "single": "Single",
    "ep": "EP",
    "compilation": "Compilação",
    "playlist": "Playlist",
    "song": "Música",
    "music_video": "Vídeo musical",
    "unknown": "Tipo desconhecido",
}


def normalize_media_item(raw_item, endpoint_type=None):
    """Normalize an Apple Music resource without guessing from its title."""
    raw_item = raw_item if isinstance(raw_item, dict) else {}
    attributes = raw_item.get("attributes") if isinstance(raw_item.get("attributes"), dict) else raw_item
    raw_type = raw_item.get("type") or endpoint_type or attributes.get("type") or "unknown"
    raw_type = str(raw_type)
    normalized_type = raw_type.lower().replace("_", "-").replace(" ", "-")
    album_type = str(attributes.get("albumType") or attributes.get("album_type") or "").lower()

    if normalized_type in {"music-videos", "music-video", "musicvideo"} or endpoint_type in {"music-videos", "music_video"}:
        category = "music_video"
    elif normalized_type in {"albums", "album"}:
        category = {"single": "single", "ep": "ep", "compilation": "compilation"}.get(album_type, "album")
    elif normalized_type in {"playlists", "playlist"}:
        category = "playlist"
    elif normalized_type in {"songs", "song", "tracks", "track"}:
        category = "song"
    else:
        category = "unknown"

    artwork = attributes.get("artwork")
    artwork_url = artwork.get("url") if isinstance(artwork, dict) else attributes.get("artworkUrl")
    if artwork_url and "{w}" in artwork_url:
        artwork_url = artwork_url.replace("{w}", "300").replace("{h}", "300")

    genres = attributes.get("genreNames")
    subtitle = attributes.get("description") or (genres[0] if isinstance(genres, list) and genres else "")
    title = attributes.get("name") or attributes.get("title") or raw_item.get("name") or ""
    release_date = attributes.get("releaseDate") or attributes.get("release_date") or ""
    return {
        "id": str(raw_item.get("id") or attributes.get("id") or ""),
        "type": category,
        "category": category,
        "category_label": MEDIA_CATEGORY_LABELS[category],
        "title": title,
        "label": title,
        "subtitle": subtitle,
        "artist": attributes.get("artistName") or attributes.get("artist_name") or "",
        "extra": attributes.get("artistName") or attributes.get("artist_name") or "",
        "releaseDate": release_date,
        "date": release_date,
        "artworkUrl": artwork_url or "",
        "isVideo": category == "music_video",
        "isAudio": category in {"album", "single", "ep", "compilation", "playlist", "song"},
        "selectable": category != "unknown",
        "rawType": raw_type,
        "raw_type": raw_type,
    }

def is_valid_apple_music_url(url: str) -> bool:
    """Basic validation: scheme http(s) and host contains music.apple.com"""
    try:
        parsed = __import__('urllib.parse').parse.urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        host = parsed.netloc.lower()
        return 'music.apple.com' in host
    except Exception:
        return False


def sanitize_title(title: str, max_len: int = 200) -> str:
    if not isinstance(title, str):
        return ''
    t = title.strip()
    if len(t) > max_len:
        return t[:max_len]
    return t

def get_config_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "apple-music-downloader", "config.yaml")

def get_config():
    try:
        with open(get_config_path(), 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except: return {}

def save_config(new_config):
    try:
        with open(get_config_path(), 'w', encoding='utf-8') as f:
            yaml.dump(new_config, f, default_flow_style=False, allow_unicode=True)
        return True
    except: return False

def validate_config_payload(payload):
    if not isinstance(payload, dict):
        return False, None, "Payload inválido."

    # Accept partial payloads: validate only provided keys and return a
    # normalized subset that can be merged with existing configuration.
    normalized = {}
    for key, value in payload.items():
        if key in STRING_CONFIG_KEYS:
            if not isinstance(value, str):
                return False, None, f"Valor inválido para '{key}'."
            normalized[key] = value.strip()
        elif key in BOOL_CONFIG_KEYS:
            if not isinstance(value, bool):
                return False, None, f"Valor inválido para '{key}'."
            normalized[key] = value
        else:
            return False, None, f"Chave desconhecida: '{key}'."

    return True, normalized, None

def analyze_label_metadata(raw_label):
    clean_label = raw_label.strip()
    release_type = "Album" # Padrão
    tags = []

    release_type = "Unknown"



    # Detecta Tags Extras (Edições)
    if re.search(r'Deluxe', clean_label, re.IGNORECASE): tags.append("Deluxe")
    if re.search(r'Remaster', clean_label, re.IGNORECASE): tags.append("Remaster")
    if re.search(r'Live', clean_label, re.IGNORECASE): tags.append("Live")
    if re.search(r'Soundtrack|OST', clean_label, re.IGNORECASE): tags.append("OST")
    if re.search(r'Expanded', clean_label, re.IGNORECASE): tags.append("Expanded")

    # Limpeza final de traços soltos no final da string
    clean_label = re.sub(r'\s-\s*$', '', clean_label).strip()

    return {"label": clean_label, "type": release_type, "tags": tags}

def fetch_metadata(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200: return None
        
        html = response.text
        title = "Unknown"
        image = ""
        
        tm = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        if tm: title = tm.group(1).replace(" | Apple Music", "")
        
        im = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        if im: image = im.group(1)
        
        type_str = "Link"
        if "/album/" in url: type_str = "Album"
        elif "/playlist/" in url: type_str = "Playlist"
        elif "/artist/" in url: type_str = "Artist"
        elif "/music-video/" in url: type_str = "Music Video"
        
        return {"title": title, "image": image, "type": type_str}
    except: return None

def generate_m3u_playlist(base_folder_key):
    # (Mantém o código da playlist que te passei anteriormente, sem alterações aqui)
    try:
        config = get_config()
        if not config: return
        
        config_key_map = {"alac": "alac-save-folder", "atmos": "atmos-save-folder", "aac": "aac-save-folder"}
        folder_name = config.get(config_key_map.get(base_folder_key), "")
        if not folder_name: return

        if not folder_name.startswith("downloads"):
             folder_name = os.path.join("downloads", os.path.basename(folder_name))
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        search_path = os.path.join(base_dir, "apple-music-downloader", folder_name)

        if not os.path.exists(search_path): return

        subdirs = [os.path.join(search_path, d) for d in os.listdir(search_path) if os.path.isdir(os.path.join(search_path, d))]
        if not subdirs: return
        latest_subdir = max(subdirs, key=os.path.getmtime)

        music_files = []
        target_dir = latest_subdir 

        nested_subdirs = [os.path.join(latest_subdir, d) for d in os.listdir(latest_subdir) if os.path.isdir(os.path.join(latest_subdir, d))]
        if nested_subdirs:
            target_dir = max(nested_subdirs, key=os.path.getmtime)
        
        files = sorted([f for f in os.listdir(target_dir) if f.lower().endswith(('.m4a', '.flac', '.mp3', '.wav'))])
        
        if files:
            playlist_name = os.path.basename(target_dir)
            playlist_file = os.path.join(target_dir, f"{playlist_name}.m3u8")
            
            with open(playlist_file, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for file in files: f.write(f"{file}\n")
            
            return f"Playlist criada: {playlist_name}.m3u8"
            
    except Exception as e: 
        print(f"Erro M3U: {e}")
        return None
