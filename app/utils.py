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