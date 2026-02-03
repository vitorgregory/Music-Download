from flask import render_template, request, jsonify
from urllib.parse import urlparse, parse_qs
from . import app, limiter, csrf
from .process_manager import wrapper, downloader
from .utils import fetch_metadata, get_config, save_config, validate_config_payload, is_valid_apple_music_url, sanitize_title
from .crypto import encrypt_str, decrypt_str
from app.queue_manager import add_to_queue, get_queue_status, set_pause, cancel_current_task, cancel_pending_task, move_queue_item, STALL_TIMEOUT_SECONDS   
import os
import json
import time
import shutil
from flask import current_app

def get_cred_path(): 
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", ".credentials")

def load_creds():
    try:
        if os.path.exists(get_cred_path()):
            with open(get_cred_path(), 'r') as f:
                c = json.load(f)
            try:
                return decrypt_str(c.get("email")), decrypt_str(c.get("password"))
            except Exception:
                # If decryption fails, return None to avoid using corrupted creds
                return None, None
    except: pass
    return None, None

def save_creds(e, p):
    try:
        os.makedirs(os.path.dirname(get_cred_path()), exist_ok=True)
        with open(get_cred_path(), 'w') as f:
            json.dump({"email": encrypt_str(e), "password": encrypt_str(p)}, f)
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
@limiter.exempt
def get_state():
    # Endpoint Unificado para reduzir chamadas HTTP (Melhor performance)
    w_status = wrapper.get_status()
    d_status = downloader.get_status()
    q_status = get_queue_status()
    # Enrich queue items with `existing_path` when progress contains our marker
    items = []
    for it in q_status.get('items', []):
        try:
            if isinstance(it.get('progress'), str) and it.get('progress', '').startswith('Exists at '):
                it['existing_path'] = it.get('progress').replace('Exists at ', '')
            else:
                it['existing_path'] = None
        except Exception:
            it['existing_path'] = None
        items.append(it)
    q_status['items'] = items
    
    # Detect whether required external components exist on disk
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wrapper_path = os.path.join(base_dir, 'wrapper', 'wrapper')
    downloader_dir = os.path.join(base_dir, 'apple-music-downloader')

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
        "downloader_last_output": d_status.get('last_output_at'),
        "downloader_stalled": (True if (d_status.get('last_output_at') and (time.time() - d_status.get('last_output_at', 0) > STALL_TIMEOUT_SECONDS)) else False),
        "queue": {
            "items": q_status["items"],
            "paused": q_status["paused"]
        }
        ,
        "wrapper_installed": os.path.exists(wrapper_path),
        "downloader_installed": os.path.isdir(downloader_dir)
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
    
    fmt_raw = (request.form.get("format") or "").strip().lower()
    if fmt_raw not in ("alac", "aac", "atmos"):
        fmt_raw = "alac"

    if not link or not is_valid_apple_music_url(link):
        return jsonify({"status": "error", "message": "Link inválido."}), 400

    title = sanitize_title(title)

    add_to_queue(link, fmt_raw, title)
    return jsonify({"status": "ok", "format": fmt_raw})


# API alias for integration tests / ZimaOS manifest
@app.route('/api/add_to_queue', methods=['POST'])
@limiter.limit("10 per minute")
def api_add_to_queue():
    payload = request.get_json(silent=True) or {}
    link = payload.get('link') or request.form.get('link')
    title = payload.get('title') or request.form.get('title')
    fmt_raw = (payload.get('format') or request.form.get('format') or "").strip().lower()
    if fmt_raw not in ("alac", "aac", "atmos"):
        fmt_raw = "alac"

    if not link or not is_valid_apple_music_url(link):
        return jsonify({"status": "error", "message": "Link inválido."}), 400

    title = sanitize_title(title)
    add_to_queue(link, fmt_raw, title)
    return jsonify({"status": "ok", "format": fmt_raw})

# --- Controles ---

@app.route("/api/pause_queue", methods=["POST"])
def pause_queue():
    paused = bool(request.json.get("paused"))
    return jsonify({"paused": set_pause(paused)})

@app.route("/api/cancel_task", methods=["POST"])
def cancel_task():
    task_id = request.json.get("id")
    status = request.json.get("status")
    if status == "pending":
        cancel_pending_task(task_id)
    else:
        cancel_current_task(task_id)
    return jsonify({"status": "ok"})

@app.route("/api/move_queue", methods=["POST"])
def move_queue():
    task_id = request.json.get("id")
    direction = request.json.get("direction")
    moved = False
    if direction in ("up", "down"):
        moved = move_queue_item(task_id, direction)
    return jsonify({"status": "ok", "moved": moved})

@app.route("/analyze_link", methods=["POST"])
def analyze():
    link = request.form.get("link")
    if not link or not is_valid_apple_music_url(link):
        return jsonify({"status": "error", "message": "Link inválido."}), 400
    meta = fetch_metadata(link)
    return jsonify({"status": "ok", "metadata": meta}) if meta else jsonify({"status": "error"})


@app.route("/login_wrapper", methods=["POST"])
def login_wrapper():
    email = (request.form.get("email") or "").strip()
    password = (request.form.get("password") or "").strip()
    if not email or not password:
        return jsonify({"status": "error", "message": "Credenciais inválidas."}), 400
    
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
    code = (request.form.get("twofa_code") or "").strip()
    if not code:
        return jsonify({"status": "error", "message": "Código 2FA inválido."}), 400
    wrapper.write_input(code)
    return jsonify({"status": "ok"})

@app.route("/submit_selection", methods=["POST"])
def submit_selection():
    sel = (request.form.get("selection") or "").strip()
    if not sel or not sel.isdigit():
        return jsonify({"status": "error", "message": "Seleção inválida."}), 400
    downloader.write_input(sel)
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
@csrf.exempt
def save_cfg():
    # Debug: log incoming headers and raw body to help diagnose client requests
    try:
        raw = request.get_data(as_text=True)
        current_app.logger.debug("/save_config headers: %s", dict(request.headers))
        current_app.logger.debug("/save_config raw body: %s", raw)
    except Exception:
        pass

    # Try JSON payload first, fall back to form-encoded data for older clients
    payload = request.get_json(silent=True)
    if payload is None:
        # Convert ImmutableMultiDict to plain dict
        try:
            payload = {k: v for k, v in request.form.items()}
        except Exception:
            payload = {}

    # Coerce boolean-like strings for checkbox fields
    try:
        from .utils import BOOL_CONFIG_KEYS
        for k in list(payload.keys()):
            if k in BOOL_CONFIG_KEYS:
                val = payload.get(k)
                if isinstance(val, str):
                    payload[k] = val.lower() in ('1', 'true', 'on', 'yes')
    except Exception:
        pass

    current_app.logger.debug("Save config payload received: %s", payload)

    # Filter payload to known config keys to avoid rejecting unexpected fields
    try:
        from .utils import STRING_CONFIG_KEYS, BOOL_CONFIG_KEYS
        allowed = set(STRING_CONFIG_KEYS) | set(BOOL_CONFIG_KEYS)
        filtered = {k: v for k, v in (payload or {}).items() if k in allowed}
        ignored = [k for k in (payload or {}).keys() if k not in allowed]
        if ignored:
            current_app.logger.debug("Ignored unknown config keys: %s", ignored)
    except Exception:
        filtered = payload or {}

    is_valid, normalized, error_message = validate_config_payload(filtered)
    if not is_valid:
        try:
            current_app.logger.error("Invalid config payload: %s -> %s", payload, error_message)
        except Exception:
            pass
        # Include the received payload in the response to help frontend debugging
        return jsonify({"status": "error", "message": error_message, "received": payload}), 400

    # Merge normalized values with existing config so partial updates work
    try:
        existing = get_config() or {}
        existing.update(normalized)
        if not save_config(existing):
            current_app.logger.error("Failed to persist config: %s", existing)
            return jsonify({"status": "error", "message": "Falha ao salvar configuração."}), 500
        return jsonify({"status":"ok", "message": "Configurações salvas."})
    except Exception as ex:
        current_app.logger.exception("Exception while saving config")
        return jsonify({"status": "error", "message": "Falha ao salvar configuração."}), 500

@app.route("/delete_saved_credentials", methods=["POST"])
def del_cred():
    if os.path.exists(get_cred_path()): os.remove(get_cred_path())
    return jsonify({"status": "ok"})


@app.route('/health', methods=['GET'])
def health():
    """Health endpoint used by container orchestrators to verify the app is alive.

    Returns basic OK status and optional DB existence flag.
    """
    # Simple DB check: ensure the DB file exists and is readable
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'queue.db')
    db_exists = os.path.exists(db_path)
    return jsonify({"status": "ok", "db": db_exists})


@app.route('/dashboard')
def dashboard():
    """Simple monitoring dashboard for ZimaOS - returns JSON with quick stats."""
    # Queue stats
    conn = None
    try:
        from app.queue_manager import get_db_connection
        conn = get_db_connection()
        stats = conn.execute("SELECT status, COUNT(*) as cnt FROM queue GROUP BY status").fetchall()
        queue_stats = {row['status']: row['cnt'] for row in stats}
        recent = conn.execute("SELECT id, title, progress, created_at FROM queue WHERE status='completed' ORDER BY id DESC LIMIT 10").fetchall()
        recent_downloads = [dict(r) for r in recent]
    except Exception:
        queue_stats = {}
        recent_downloads = []
    finally:
        if conn: conn.close()

    # Storage usage (downloads dir)
    # Downloads directory at repo root: ../downloads relative to this file
    downloads_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'downloads'))
    storage_usage = {}
    try:
        total = 0
        if os.path.exists(downloads_path):
            for root, dirs, files in os.walk(downloads_path):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except Exception:
                        pass
        storage_usage['downloads_bytes'] = total
    except Exception:
        storage_usage['downloads_bytes'] = None

    # System health: wrapper/downloader basic state
    try:
        w = wrapper.get_status()
        d = downloader.get_status()
        system_health = {'wrapper_running': w.get('running'), 'downloader_running': d.get('running')}
    except Exception:
        system_health = {}

    return jsonify({
        'queue_stats': queue_stats,
        'recent_downloads': recent_downloads,
        'storage_usage': storage_usage,
        'system_health': system_health
    })
