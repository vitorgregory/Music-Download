from flask import render_template, request, jsonify
from urllib.parse import urlparse, parse_qs
from . import app
from .process_manager import wrapper, downloader
from .utils import fetch_metadata, get_config, save_config
from app.queue_manager import add_to_queue, get_queue_status, set_pause, cancel_current_task   
import os
import json
import base64
import time
import shutil

def get_cred_path(): 
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", ".credentials")

def load_creds():
    try:
        if os.path.exists(get_cred_path()):
            with open(get_cred_path(), 'r') as f: c = json.load(f)
            return base64.b64decode(c["email"]).decode(), base64.b64decode(c["password"]).decode()
    except: pass
    return None, None

def save_creds(e, p):
    try:
        os.makedirs(os.path.dirname(get_cred_path()), exist_ok=True)
        with open(get_cred_path(), 'w') as f: 
            json.dump({"email": base64.b64encode(e.encode()).decode(), "password": base64.b64encode(p.encode()).decode()}, f)
    except: pass

# --- Rotas Principais ---

@app.route("/")
def index():
    # Tenta auto-login se tiver credenciais salvas
    creds = load_creds()
    if creds[0] and not wrapper.running:
        wrapper.start(creds[0], creds[1])
    return render_template("index.html")

@app.route("/settings")
def settings(): 
    return render_template("settings.html")

# --- API ---

@app.route("/api/state", methods=["GET"])
def get_state():
    # Endpoint Unificado para reduzir chamadas HTTP (Melhor performance)
    w_status = wrapper.get_status()
    d_status = downloader.get_status()
    q_status = get_queue_status()
    
    return jsonify({
        "wrapper": {
            "running": w_status["running"],
            "logs": w_status["logs"],
            "needs_2fa": wrapper.needs_2fa
        },
        "downloader": {
            "running": d_status["running"],
            "logs": d_status["logs"],
            "needs_selection": d_status["needs_input"],
            "options": d_status["options"]
        },
        "queue": {
            "items": q_status["items"],
            "paused": q_status["paused"]
        }
    })

@app.route("/download", methods=["POST"])
def download():
    link = request.form.get("link")
    title = request.form.get("title")
    
    if link:
        # Lógica de limpeza de URL (Mantém parâmetro ?i= para singles)
        if "?i=" in link or "&i=" in link:
            try:
                parsed = urlparse(link)
                i_val = parse_qs(parsed.query).get('i')
                base = link.split("?")[0]
                if i_val: link = f"{base}?i={i_val[0]}"
            except: pass
        elif "?" in link:
            link = link.split("?")[0]
    
    special = request.form.get("special_audio") == "true"
    fmt_raw = request.form.get("format")
    
    fmt = "alac"
    if special:
        if fmt_raw == "ATMOS": fmt = "atmos"
        elif fmt_raw == "AAC": fmt = "aac"
    
    add_to_queue(link, fmt, title)
    return jsonify({"status": "ok"})

# --- Controles ---

@app.route("/api/pause_queue", methods=["POST"])
def pause_queue():
    paused = request.json.get("paused")
    return jsonify({"paused": set_pause(paused)})

@app.route("/api/cancel_task", methods=["POST"])
def cancel_task():
    cancel_current_task(request.json.get("id"))
    return jsonify({"status": "ok"})

@app.route("/analyze_link", methods=["POST"])
def analyze():
    meta = fetch_metadata(request.form.get("link"))
    return jsonify({"status": "ok", "metadata": meta}) if meta else jsonify({"status": "error"})


@app.route("/login_wrapper", methods=["POST"])
def login_wrapper():
    email = request.form.get("email")
    password = request.form.get("password")
    
    # 1. Para o processo atual
    wrapper.stop()
    time.sleep(1)
    # 2. Limpa cache antigo
    wrapper_dir = os.path.dirname(os.path.join(os.path.dirname(os.path.abspath(__file__)), "wrapper", "wrapper"))
    
    try:
        for item in os.listdir(wrapper_dir):
            if item.endswith(".json") or item == "cache":
                path = os.path.join(wrapper_dir, item)
                if os.path.isfile(path):
                    os.remove(path)
                    print(f"[LOGIN] Cache deletado: {item}")
                elif os.path.isdir(path):
                    shutil.rmtree(path)
                    print(f"[LOGIN] Pasta cache deletada: {item}")
    except Exception as e:
        print(f"[LOGIN WARNING] Falha ao limpar cache: {e}")

    # 3. Inicia do zero
    if wrapper.start(email, password):
        save_creds(email, password)
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})

@app.route("/stop_wrapper", methods=["POST"])
def stop_wrapper():
    wrapper.stop()
    return jsonify({"status": "ok"})

@app.route("/submit_2fa", methods=["POST"])
def submit_2fa():
    wrapper.write_input(request.form.get("twofa_code"))
    return jsonify({"status": "ok"})

@app.route("/submit_selection", methods=["POST"])
def submit_selection():
    downloader.write_input(request.form.get("selection"))
    return jsonify({"status": "ok"})

@app.route("/skip_selection", methods=["POST"])
def skip_selection():
    downloader.close_stdin()
    return jsonify({"status": "ok"})

# --- Configs ---

@app.route("/get_config")
def get_cfg(): 
    return jsonify({"status":"ok", "config": get_config()})

@app.route("/save_config", methods=["POST"])
def save_cfg():
    save_config(request.json)
    return jsonify({"status":"ok"})

@app.route("/delete_saved_credentials", methods=["POST"])
def del_cred():
    if os.path.exists(get_cred_path()): os.remove(get_cred_path())
    return jsonify({"status": "ok"})