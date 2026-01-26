from flask import render_template, request, jsonify
from . import app
from .process_manager import wrapper, downloader
from .utils import fetch_metadata, get_config
import os
import json
import base64

# --- Credenciais Helpers ---
def get_cred_path(): 
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".credentials")

def save_creds(e, p):
    try:
        with open(get_cred_path(), 'w') as f: 
            json.dump({"email": base64.b64encode(e.encode()).decode(), "password": base64.b64encode(p.encode()).decode()}, f)
    except: pass

def load_creds():
    try:
        if os.path.exists(get_cred_path()):
            with open(get_cred_path(), 'r') as f: c = json.load(f)
            return base64.b64decode(c["email"]).decode(), base64.b64decode(c["password"]).decode()
    except: pass
    return None, None

def delete_creds():
    if os.path.exists(get_cred_path()): os.remove(get_cred_path())

# --- Routes ---

@app.route("/")
def index():
    creds = load_creds()
    # Tenta auto-login se tiver credenciais e wrapper parado
    if creds[0] and not wrapper.running:
        wrapper.start(creds[0], creds[1])
    return render_template("index.html")

@app.route("/get_logs")
def get_logs():
    w_status = wrapper.get_status()
    d_status = downloader.get_status()
    
    return jsonify({
        "wrapper": w_status["logs"],
        "wrapper_running": w_status["running"],
        "wrapper_needs_2fa": wrapper.needs_2fa,
        
        "downloader": d_status["logs"],
        "download_running": d_status["running"],
        "download_needs_selection": d_status["needs_input"],
        "selection_options": d_status["options"]
    })

@app.route("/login_wrapper", methods=["POST"])
def login_wrapper():
    email = request.form.get("email")
    password = request.form.get("password")
    if wrapper.start(email, password):
        save_creds(email, password)
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "msg": "Failed to start wrapper"})

@app.route("/stop_wrapper", methods=["POST"])
def stop_wrapper():
    wrapper.stop()
    return jsonify({"status": "ok"})

@app.route("/submit_2fa", methods=["POST"])
def submit_2fa():
    if wrapper.write_input(request.form.get("twofa_code")):
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})

@app.route("/analyze_link", methods=["POST"])
def analyze():
    meta = fetch_metadata(request.form.get("link"))
    return jsonify({"status": "ok", "metadata": meta}) if meta else jsonify({"status": "error"})

@app.route("/download", methods=["POST"])
def download():
    link = request.form.get("link")
    special = request.form.get("special_audio") == "true"
    fmt = request.form.get("format")
    
    args = []
    if special:
        if fmt == "ATMOS": args = ["--atmos"]
        elif fmt == "AAC": args = ["--aac"]
    
    if downloader.start(link, args):
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "msg": "Failed to start download"})

@app.route("/submit_selection", methods=["POST"])
def submit_selection():
    if downloader.write_input(request.form.get("selection")):
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})

@app.route("/skip_selection", methods=["POST"])
def skip_selection():
    if downloader.close_stdin():
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})

@app.route("/cancel_download", methods=["POST"])
def cancel_download():
    downloader.stop()
    return jsonify({"status": "ok"})

# --- Settings & Misc ---
@app.route("/settings")
def settings(): return render_template("settings.html")

@app.route("/get_config")
def get_cfg(): return jsonify({"status":"ok", "config": get_config()})

@app.route("/check_saved_credentials")
def check_cred():
    c = load_creds()
    return jsonify({"has_credentials": c[0] is not None, "email": c[0] or ""})

@app.route("/delete_saved_credentials", methods=["POST"])
def del_cred():
    delete_creds()
    return jsonify({"status": "ok"})

@app.route("/get_download_folders")
def get_folders():
    c = get_config()
    return jsonify({"status":"ok", "folders": {
        "alac": c.get("alac-save-folder", "AM-DL"),
        "atmos": c.get("atmos-save-folder", "AM-DL-Atmos"),
        "aac": c.get("aac-save-folder", "AM-DL-AAC")
    }})