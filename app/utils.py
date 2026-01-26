import re
import requests
import yaml
import os

def strip_ansi(text):
    """Remove códigos de cor do terminal"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def get_config():
    """Lê configuração do YAML"""
    try:
        # Ajuste o caminho conforme sua estrutura
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "apple-music-downloader", "config.yaml")
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Config Error: {e}")
        return {}

def analyze_label_metadata(raw_label):
    """Analisa o nome da música/álbum para identificar tipo (Single, EP, etc)"""
    clean_label = raw_label.strip()
    release_type = "Album"
    tags = []

    # Regex Case Insensitive
    if re.search(r'\b(Single)\b', clean_label, re.IGNORECASE):
        release_type = "Single"
        clean_label = re.sub(r'[\(\[\-]\s*Single\s*[\)\]]?', '', clean_label, flags=re.IGNORECASE)
        clean_label = re.sub(r'\s-\s*Single$', '', clean_label, flags=re.IGNORECASE)
    elif re.search(r'\b(EP)\b', clean_label, re.IGNORECASE):
        release_type = "EP"
        clean_label = re.sub(r'\s-\s*EP$', '', clean_label, flags=re.IGNORECASE)

    if re.search(r'Deluxe', clean_label, re.IGNORECASE): tags.append("Deluxe")
    if re.search(r'Remaster', clean_label, re.IGNORECASE): tags.append("Remaster")
    if re.search(r'Live', clean_label, re.IGNORECASE): tags.append("Live")
    if re.search(r'Soundtrack', clean_label, re.IGNORECASE): tags.append("OST")

    clean_label = re.sub(r'\s-\s*$', '', clean_label).strip()

    return {
        "label": clean_label,
        "type": release_type,
        "tags": tags
    }

def fetch_metadata(url):
    """Busca título e imagem da URL da Apple Music"""
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
    except:
        return None