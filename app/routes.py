import subprocess
import threading
from flask import render_template, request, jsonify
import shlex
import yaml
import os
import json
import base64
import time
import glob
import re
import requests
from . import app

wrapper_process = None
wrapper_running = False
wrapper_needs_2fa = False

download_process = None
download_running = False
download_needs_selection = False
download_selection_options = []

def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def get_config_data():
    try:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(script_dir, "apple-music-downloader", "config.yaml")
        with open(config_path, 'r', encoding='utf-8') as f: return yaml.safe_load(f)
    except: return None

# --- Analisador de Tipos Aprimorado ---
def analyze_label_metadata(raw_label):
    clean_label = raw_label.strip()
    release_type = "Album" # Default
    tags = []

    # Regex para encontrar padrões ignorando Case
    # Detecta Single
    if re.search(r'\b(Single)\b', clean_label, re.IGNORECASE):
        release_type = "Single"
        # Remove a palavra do nome para limpar visualmente
        clean_label = re.sub(r'[\(\[\-]\s*Single\s*[\)\]]?', '', clean_label, flags=re.IGNORECASE)
        clean_label = re.sub(r'\s-\s*Single$', '', clean_label, flags=re.IGNORECASE)

    # Detecta EP
    elif re.search(r'\b(EP)\b', clean_label, re.IGNORECASE):
        release_type = "EP"
        # Remove EP do final se estiver como " - EP"
        clean_label = re.sub(r'\s-\s*EP$', '', clean_label, flags=re.IGNORECASE)

    # Detecta Tags Extras
    if re.search(r'Deluxe', clean_label, re.IGNORECASE): tags.append("Deluxe")
    if re.search(r'Remaster', clean_label, re.IGNORECASE): tags.append("Remaster")
    if re.search(r'Live', clean_label, re.IGNORECASE): tags.append("Live")
    if re.search(r'Soundtrack', clean_label, re.IGNORECASE): tags.append("OST")

    # Limpeza final de traços soltos no final da string
    clean_label = re.sub(r'\s-\s*$', '', clean_label).strip()

    return {
        "label": clean_label,
        "type": release_type,
        "tags": tags
    }

def get_apple_music_metadata(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200: return None
        html = response.text
        
        title = "Unknown"
        image = ""
        type_str = "Link"
        
        tm = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        if tm: title = tm.group(1).replace(" | Apple Music", "")
        
        im = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        if im: image = im.group(1)
        
        if "/album/" in url: type_str = "Album"
        elif "/playlist/" in url: type_str = "Playlist"
        elif "/artist/" in url: type_str = "Artist"
        elif "/music-video/" in url: type_str = "Music Video"
        
        return {"title": title, "image": image, "type": type_str}
    except: return None

def generate_m3u_playlist(base_folder_key):
    try:
        config = get_config_data()
        if not config: return
        config_key_map = {"alac": "alac-save-folder", "atmos": "atmos-save-folder", "aac": "aac-save-folder"}
        folder_path = config.get(config_key_map.get(base_folder_key), "")
        if not folder_path: return
        if not os.path.isabs(folder_path):
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            amd_dir = os.path.join(script_dir, "apple-music-downloader")
            search_path = os.path.join(amd_dir, folder_path)
        else: search_path = folder_path
        subdirs = glob.glob(os.path.join(search_path, "*"))
        subdirs = [d for d in subdirs if os.path.isdir(d)]
        if not subdirs: return
        latest_subdir = max(subdirs, key=os.path.getmtime)
        album_name = os.path.basename(latest_subdir)
        playlist_file = os.path.join(latest_subdir, f"{album_name}.m3u8")
        music_files = sorted([f for f in os.listdir(latest_subdir) if f.lower().endswith(('.m4a', '.flac', '.mp3', '.wav'))])
        if music_files:
            with open(playlist_file, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for file in music_files: f.write(f"{file}\n")
            return f"Playlist criada: {album_name}.m3u8"
    except: return None

def stream_download_logs(pipe, target_list, format_type="alac"):
    global download_running, download_process, download_needs_selection, download_selection_options
    
    SELECTION_KEYWORDS = ["Select:", "Enter choice", "Input:", "(default: All)", "Choice:", "selection:", "Select options", "Choose:"]
    log_buffer = []

    def check_keywords(text):
        clean = strip_ansi(text)
        for kw in SELECTION_KEYWORDS:
            if kw.lower() in clean.lower(): return True
        return False

    def parse_options(buffer):
        options = []
        # Regex Aprimorada para pegar 3 colunas: ID | NOME | DATA
        # Ex: | 1 | Album Name | 2023-01-01 |
        regex_table = r"^\s*\|\s*(\d+)\s*\|\s*([^\|]+)\s*\|\s*([^\|]+)"
        
        # Regex Lista Simples
        regex_list = r"(?:^|\s|\[\w+\]\s+)(\d+)\s*[\.\:\-\)\]]\s+(.+)$"
        
        for line in reversed(buffer[-200:]):
            clean = strip_ansi(line).strip()
            if not clean or any(k.lower() in clean.lower() for k in SELECTION_KEYWORDS): continue
            if "+---" in clean or "ALBUM NAME" in clean: continue
            
            # Tabela (Com Data)
            if "|" in clean:
                m = re.search(regex_table, clean)
                if m: 
                    raw_name = m.group(2).strip()
                    date_info = m.group(3).strip()
                    meta = analyze_label_metadata(raw_name)
                    
                    options.insert(0, {
                        "id": m.group(1), 
                        "label": meta['label'], 
                        "type": meta['type'], 
                        "tags": meta['tags'],
                        "date": date_info  # Nova info
                    })
                    continue
            
            # Lista (Sem Data)
            m = re.search(regex_list, clean)
            if m: 
                meta = analyze_label_metadata(m.group(2).strip())
                options.insert(0, {
                    "id": m.group(1), 
                    "label": meta['label'], 
                    "type": meta['type'], 
                    "tags": meta['tags'],
                    "date": "" 
                })
            elif len(options) > 0 and "|" not in clean: break
        return options

    try:
        buffer_str = ""
        while True:
            char = pipe.read(1)
            if not char: break
            buffer_str += char
            if char == '\n':
                line = buffer_str.strip()
                if line:
                    target_list.append(line)
                    print(f"[DL] {line}")
                    log_buffer.append(line)
                    if check_keywords(line):
                        opts = parse_options(log_buffer)
                        download_selection_options = opts if opts else []
                        download_needs_selection = True
                        target_list.append(">>> AGUARDANDO SELEÇÃO <<<")
                buffer_str = ""
            elif len(buffer_str) > 300 or buffer_str.endswith(": ") or buffer_str.endswith("? "):
                if check_keywords(buffer_str):
                    line = buffer_str.strip()
                    target_list.append(line)
                    log_buffer.append(line)
                    opts = parse_options(log_buffer)
                    download_selection_options = opts if opts else []
                    download_needs_selection = True
                    target_list.append(">>> AGUARDANDO SELEÇÃO <<<")
                    buffer_str = ""
    except Exception as e: target_list.append(f"Error: {e}")
    finally:
        if download_process:
            if download_process.poll() is None: pass
            elif download_process.poll() == 0:
                target_list.append("Process finished.")
                msg = generate_m3u_playlist(format_type.lower())
                if msg: target_list.append(f"✅ {msg}")
            else: target_list.append(f"Ended (Code: {download_process.poll()})")
        download_running = False
        download_needs_selection = False
        pipe.close()

def stream_wrapper_logs(pipe, target_list, email, password, auto_login):
    global wrapper_running, wrapper_process, wrapper_needs_2fa
    success = False
    try:
        for line in iter(pipe.readline, ''):
            line = line.strip()
            if line:
                clean = strip_ansi(line)
                target_list.append(line)
                if "credentialhandler" in clean.lower() and "2fa" in clean.lower():
                    wrapper_needs_2fa = True
                if "[.] response type 6" in clean:
                    wrapper_running = True
                    wrapper_needs_2fa = False
                    success = True
                    if email and password: save_credentials(email, password)
    finally:
        wrapper_running = False
        if not success and auto_login: delete_credentials()
        pipe.close()

# --- Credenciais (Mantidas) ---
def get_credentials_path(): return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".credentials")
def save_credentials(e, p):
    try:
        with open(get_credentials_path(), 'w') as f: json.dump({"email": base64.b64encode(e.encode()).decode(), "password": base64.b64encode(p.encode()).decode()}, f)
    except: pass
def load_credentials():
    try:
        if os.path.exists(get_credentials_path()):
            with open(get_credentials_path(), 'r') as f: c = json.load(f)
            return base64.b64decode(c["email"]).decode(), base64.b64decode(c["password"]).decode()
    except: pass
    return None, None
def delete_credentials():
    try:
        if os.path.exists(get_credentials_path()): os.remove(get_credentials_path())
    except: pass

def start_wrapper_login(email, password, auto_login=False):
    global wrapper_process, wrapper_running, wrapper_logs
    if wrapper_process and wrapper_process.poll() is None: return False
    if not auto_login: wrapper_logs = []
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wrapper_path = os.path.join(script_dir, "wrapper", "wrapper")
    try:
        env = os.environ.copy()
        env["TERM"] = "dumb"
        wrapper_process = subprocess.Popen([wrapper_path, "-L", f"{email}:{password}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, bufsize=1, universal_newlines=True, cwd=os.path.dirname(wrapper_path), env=env)
        threading.Thread(target=stream_wrapper_logs, args=(wrapper_process.stdout, wrapper_logs, email, password, auto_login), daemon=True).start()
        return True
    except: return False

wrapper_logs = []
downloader_logs = []

# --- ROTAS ---
@app.route("/")
def index():
    e, p = load_credentials()
    if e and p and not wrapper_running: threading.Thread(target=lambda: start_wrapper_login(e, p, True), daemon=True).start()
    return render_template("index.html", wrapper_running=wrapper_running, has_saved_credentials=e is not None, saved_email=e if e else "")

@app.route("/login_wrapper", methods=["POST"])
def login_wrapper():
    if start_wrapper_login(request.form.get("email"), request.form.get("password")): return jsonify({"status":"ok"})
    return jsonify({"status":"error"})

@app.route("/submit_2fa", methods=["POST"])
def submit_2fa():
    global wrapper_needs_2fa
    if wrapper_process:
        wrapper_process.stdin.write(f"{request.form.get('twofa_code')}\n")
        wrapper_process.stdin.flush()
        wrapper_needs_2fa = False
        return jsonify({"status":"ok"})
    return jsonify({"status":"error"})

@app.route("/stop_wrapper", methods=["POST"])
def stop_wrapper():
    if wrapper_process: wrapper_process.terminate()
    return jsonify({"status":"ok"})

@app.route("/analyze_link", methods=["POST"])
def analyze_link():
    meta = get_apple_music_metadata(request.form.get("link"))
    return jsonify({"status":"ok", "metadata":meta}) if meta else jsonify({"status":"error"})

@app.route("/download", methods=["POST"])
def download():
    global download_process, download_running, downloader_logs, download_needs_selection, download_selection_options
    if not wrapper_running: return jsonify({"status":"error", "msg":"Wrapper stopped"})
    if download_running: return jsonify({"status":"error", "msg":"Busy"})
    
    link = request.form.get("link")
    special = request.form.get("special_audio") == "true"
    fmt = request.form.get("format")
    
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    amd_dir = os.path.join(script_dir, "apple-music-downloader")
    cmd = ["go", "run", "main.go"]
    if special: cmd.extend(["--atmos", link] if fmt=="ATMOS" else ["--aac", link])
    else: cmd.append(link)
    
    downloader_logs = [f"Starting: {link}"]
    download_needs_selection = False
    download_selection_options = []
    
    try:
        env = os.environ.copy()
        env["TERM"] = "dumb"
        download_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, bufsize=1, universal_newlines=True, cwd=amd_dir, env=env)
        download_running = True
        threading.Thread(target=stream_download_logs, args=(download_process.stdout, downloader_logs, "atmos" if fmt=="ATMOS" and special else "aac" if fmt=="AAC" and special else "alac"), daemon=True).start()
        return jsonify({"status":"ok"})
    except Exception as e: return jsonify({"status":"error", "msg":str(e)})

@app.route("/submit_selection", methods=["POST"])
def submit_selection():
    global download_needs_selection
    if download_process:
        try:
            download_process.stdin.write(f"{request.form.get('selection')}\n")
            download_process.stdin.flush()
            downloader_logs.append(f"User Selected: {request.form.get('selection')}")
            download_needs_selection = False
            return jsonify({"status":"ok"})
        except Exception as e: return jsonify({"status":"error", "msg":str(e)})
    return jsonify({"status":"error"})

@app.route("/skip_selection", methods=["POST"])
def skip_selection():
    global download_needs_selection, download_running
    if download_process:
        try:
            download_process.stdin.close()
            downloader_logs.append(">>> USUÁRIO PULOU A SELEÇÃO <<<")
            download_needs_selection = False
            return jsonify({"status":"ok", "msg":"Skipped"})
        except Exception as e:
            try:
                download_process.terminate()
                download_running = False
                return jsonify({"status":"ok", "msg":"Terminated"})
            except: return jsonify({"status":"error", "msg":str(e)})
    return jsonify({"status":"error"})

@app.route("/cancel_download", methods=["POST"])
def cancel_download():
    global download_running, download_needs_selection
    if download_process:
        download_process.terminate()
        download_running = False
        download_needs_selection = False
        downloader_logs.append(">>> DOWNLOAD CANCELADO <<<")
        return jsonify({"status":"ok"})
    return jsonify({"status":"error"})

@app.route("/get_logs")
def get_logs():
    global wrapper_running, download_running
    if wrapper_process and wrapper_process.poll() is not None: wrapper_running = False
    if download_process and download_process.poll() is not None: download_running = False
    return jsonify({
        "wrapper": wrapper_logs[-200:], "downloader": downloader_logs[-200:],
        "wrapper_running": wrapper_running, "download_running": download_running,
        "wrapper_needs_2fa": wrapper_needs_2fa,
        "download_needs_selection": download_needs_selection,
        "selection_options": download_selection_options
    })

# --- Config & Misc ---
@app.route("/settings")
def settings(): return render_template("settings.html")
@app.route("/get_config")
def get_config(): return jsonify({"status":"ok", "config": get_config_data() or {}})
@app.route("/save_config", methods=["POST"])
def save_config():
    try:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "apple-music-downloader", "config.yaml")
        with open(path, 'w', encoding='utf-8') as f: yaml.dump(request.json, f)
        return jsonify({"status":"ok"})
    except: return jsonify({"status":"error"})
@app.route("/check_saved_credentials")
def check_cred(): 
    c = load_credentials()
    return jsonify({"has_credentials": c[0] is not None, "email": c[0] or ""})
@app.route("/delete_saved_credentials", methods=["POST"])
def del_cred():
    delete_credentials()
    return jsonify({"status":"ok"})
@app.route("/auto_login", methods=["POST"])
def auto_log():
    c = load_credentials()
    if c[0]: return jsonify({"status":"ok" if start_wrapper_login(c[0], c[1], True) else "error"})
    return jsonify({"status":"error"})
@app.route("/get_download_folders")
def get_folders():
    c = get_config_data() or {}
    return jsonify({"status":"ok", "folders": {"alac": c.get("alac-save-folder", "AM-DL"), "atmos": c.get("atmos-save-folder", "AM-DL-Atmos"), "aac": c.get("aac-save-folder", "AM-DL-AAC")}})