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
    "live": "Álbum ao vivo",
    "unknown": "Tipo desconhecido",
}

RELEASE_KINDS = {"album", "ep", "single", "music_video", "compilation", "unknown", "live", "playlist", "song"}


def _coerce_track_count(value):
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    return count if count >= 0 else None


def _coerce_duration_seconds(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    text = str(value).strip()
    if text.isdigit():
        return float(text)
    match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)


def normalize_release_type(raw_type, track_count=None, total_duration_sec=None, album_type=None, name=None, is_live=False, is_concert=False):
    """Return the canonical release kind using structural metadata and explicit flags."""
    raw_type = str(raw_type or "unknown")
    normalized_type = raw_type.lower().replace("_", "-").replace(" ", "-")
    album_type = str(album_type or "").lower().replace("_", "-").replace(" ", "-")
    count = _coerce_track_count(track_count)
    duration = _coerce_duration_seconds(total_duration_sec)

    title = str(name or "").strip()
    title_lower = title.lower()
    if normalized_type in {"music-video", "music-videos", "musicvideo"}:
        return "music_video"
    if is_live or is_concert or normalized_type in {"live", "concert", "concerts"}:
        return "live"
    if re.search(r"\blive\b|\bconcert\b", title_lower):
        return "live"
    if normalized_type in {"compilation", "compilations"} or album_type == "compilation":
        return "compilation"
    if normalized_type in {"playlist", "playlists"}:
        return "playlist"
    if normalized_type in {"song", "songs", "track", "tracks"}:
        return "song"
    if album_type in {"single", "ep", "album", "compilation"}:
        if album_type == "album" and re.search(r"(?:-|\s)single$", title_lower):
            return "single"
        if album_type == "album" and re.search(r"(?:-|\s)ep$", title_lower):
            return "ep"
        return album_type
    if normalized_type not in {"album", "albums"}:
        if re.search(r"(?:-|\s)single$", title_lower):
            return "single"
        if re.search(r"(?:-|\s)ep$", title_lower):
            return "ep"
        return "unknown"
    if count is None and duration is None:
        if re.search(r"(?:-|\s)single$", title_lower):
            return "single"
        if re.search(r"(?:-|\s)ep$", title_lower):
            return "ep"
        return "album"
    if (count is not None and count >= 7) or (duration is not None and duration >= 1800):
        return "album"
    if count is not None and 4 <= count <= 6 and (duration is None or duration < 1800):
        return "ep"
    if count is not None and 1 <= count <= 3 and (duration is None or duration < 1800):
        return "single"
    return "unknown"


def normalize_media_item(raw_item, endpoint_type=None):
    """Normalize an Apple Music resource without guessing from its title."""
    raw_item = raw_item if isinstance(raw_item, dict) else {}
    attributes = raw_item.get("attributes") if isinstance(raw_item.get("attributes"), dict) else raw_item
    raw_type = raw_item.get("type") or endpoint_type or attributes.get("type") or "unknown"
    raw_type = str(raw_type)
    track_count = attributes.get("trackCount", attributes.get("track_count"))
    duration = attributes.get("totalDurationSec", attributes.get("total_duration_sec"))
    duration = attributes.get("duration", duration)
    album_type = attributes.get("albumType", attributes.get("album_type"))
    category = normalize_release_type(
        raw_type,
        track_count,
        duration,
        album_type,
        name=attributes.get("name") or attributes.get("title") or raw_item.get("name"),
        is_live=attributes.get("isLive") is True or attributes.get("live") is True,
        is_concert=attributes.get("concert") is True,
    )
    track_count = _coerce_track_count(track_count)
    duration_seconds = _coerce_duration_seconds(duration)

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
        "kind": category,
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
        "isAudio": category in {"album", "single", "ep", "live", "compilation", "playlist", "song"},
        "selectable": bool(raw_item.get("id") or attributes.get("id")),
        "track_count": track_count,
        "total_duration_sec": duration_seconds,
        "duration_sec": int(duration_seconds) if duration_seconds is not None else None,
        "duration": duration or "",
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
    release_type = "Unknown"
    tags = []

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
