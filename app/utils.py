import re
import requests
import yaml
import os

def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

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

def analyze_label_metadata(raw_label):
    clean_label = raw_label.strip()
    release_type = "Album"
    tags = []

    if re.search(r'\b(Single)\b', clean_label, re.IGNORECASE):
        release_type = "Single"
        clean_label = re.sub(r'[\(\[\-]\s*Single\s*[\)\]]?', '', clean_label, flags=re.IGNORECASE)
        clean_label = re.sub(r'\s-\s*Single$', '', clean_label, flags=re.IGNORECASE)
    elif re.search(r'\b(EP)\b', clean_label, re.IGNORECASE):
        release_type = "EP"
        clean_label = re.sub(r'\s-\s*EP$', '', clean_label, flags=re.IGNORECASE)

    if re.search(r'Deluxe', clean_label, re.IGNORECASE): tags.append("Deluxe")
    if re.search(r'Remaster', clean_label, re.IGNORECASE): tags.append("Remaster")
    
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
        
        return {"title": title, "image": image, "type": type_str}
    except: return None

def generate_m3u_playlist(base_folder_key):
    try:
        config = get_config() # ou get_config_data() dependendo da sua versão
        if not config: return
        
        # Mapeia as chaves de configuração
        config_key_map = {"alac": "alac-save-folder", "atmos": "atmos-save-folder", "aac": "aac-save-folder"}
        folder_name = config.get(config_key_map.get(base_folder_key), "")
        if not folder_name: return

        # Monta o caminho real dentro do container
        # Adiciona 'downloads/' se não estiver no caminho, pois é onde o volume está montado
        if not folder_name.startswith("downloads"):
             folder_name = os.path.join("downloads", os.path.basename(folder_name))
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        search_path = os.path.join(base_dir, "apple-music-downloader", folder_name)

        if not os.path.exists(search_path): return

        # 1. Acha a pasta mais recente modificada (pode ser a do Artista ou da Playlist)
        subdirs = [os.path.join(search_path, d) for d in os.listdir(search_path) if os.path.isdir(os.path.join(search_path, d))]
        if not subdirs: return
        latest_subdir = max(subdirs, key=os.path.getmtime)

        # 2. Busca Recursiva: Procura músicas dentro da pasta recente E das subpastas dela
        music_files = []
        target_dir = latest_subdir # Onde vamos salvar o m3u

        # Se a pasta recente tiver subpastas (ex: Apple Music > Playlist X), entra nelas
        nested_subdirs = [os.path.join(latest_subdir, d) for d in os.listdir(latest_subdir) if os.path.isdir(os.path.join(latest_subdir, d))]
        if nested_subdirs:
            # Pega a subpasta mais recente (a playlist real)
            target_dir = max(nested_subdirs, key=os.path.getmtime)
        
        # Lista as músicas
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
