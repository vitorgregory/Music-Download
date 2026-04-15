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
    # Capas de Álbum
    "embed-cover",
    "save-artist-artwork",
    # Artwork Animado
    "save-animated-artwork",
    "emby-animated-artwork",
    # Letras
    "embed-lyrics",
    "save-lrc",
}

REQUIRED_CONFIG_KEYS = set(STRING_CONFIG_KEYS)

def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def get_config_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "apple-music-downloader", "config.yaml")

def get_config():
    try:
        with open(get_config_path(), 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        # Defaults para novas chaves booleanas
        cfg.setdefault("use-song-info-for-playlist", True)
        cfg.setdefault("download-album-cover-for-playlist", True)
        cfg.setdefault("embed-cover", True)
        cfg.setdefault("save-artist-artwork", False)
        cfg.setdefault("save-animated-artwork", False)
        cfg.setdefault("emby-animated-artwork", False)
        cfg.setdefault("embed-lyrics", False)
        cfg.setdefault("save-lrc", False)
        return cfg
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

    missing_keys = sorted(REQUIRED_CONFIG_KEYS - payload.keys())
    if missing_keys:
        return False, None, f"Chaves obrigatórias ausentes: {', '.join(missing_keys)}."

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

    # Detecta Music Video (Geralmente tem "Video" ou "Clip" no nome ou metadados)
    if re.search(r'\b(Video|Music Video)\b', clean_label, re.IGNORECASE):
        release_type = "Music Video"
        clean_label = re.sub(r'[\(\[\-]\s*(Music\s*)?Video\s*[\)\]]?', '', clean_label, flags=re.IGNORECASE)
        clean_label = re.sub(r'\s-\s*(Music\s*)?Video$', '', clean_label, flags=re.IGNORECASE)

    # Detecta Single
    elif re.search(r'\b(Single)\b', clean_label, re.IGNORECASE):
        release_type = "Single"
        clean_label = re.sub(r'[\(\[\-]\s*Single\s*[\)\]]?', '', clean_label, flags=re.IGNORECASE)
        clean_label = re.sub(r'\s-\s*Single$', '', clean_label, flags=re.IGNORECASE)

    # Detecta EP
    elif re.search(r'\b(EP)\b', clean_label, re.IGNORECASE):
        release_type = "EP"
        clean_label = re.sub(r'\s-\s*EP$', '', clean_label, flags=re.IGNORECASE)

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
