from pathlib import Path
from flask import render_template, request, jsonify
from urllib.parse import urlparse, parse_qs
from . import app, limiter, csrf
from .process_manager import wrapper, downloader, get_wrapper_bin_path, get_wrapper_cache_dir, get_wrapper_rootfs_path
from .utils import fetch_metadata, get_config, save_config, validate_config_payload, is_valid_apple_music_url, sanitize_title
from .crypto import encrypt_str, decrypt_str
from app.queue_manager import add_to_queue, get_queue_status, set_pause, cancel_current_task, cancel_pending_task, move_queue_item, STALL_TIMEOUT_SECONDS   
import os
import json
import time
import shutil
import threading
import tempfile
import re
from flask import current_app

def get_cred_path(): 
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", ".credentials")

def get_2fa_cache_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", ".2fa_cache")

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

def load_2fa_cache():
    """Carrega código 2FA em cache (encrypted)"""
    try:
        if os.path.exists(get_2fa_cache_path()):
            with open(get_2fa_cache_path(), 'r') as f:
                c = json.load(f)
            try:
                return decrypt_str(c.get("code"))
            except Exception:
                return None
    except: pass
    return None

def save_2fa_cache(code):
    """Salva código 2FA em cache (encrypted)"""
    try:
        os.makedirs(os.path.dirname(get_2fa_cache_path()), exist_ok=True)
        with open(get_2fa_cache_path(), 'w') as f:
            json.dump({"code": encrypt_str(code)}, f)
    except: pass

def clear_2fa_cache():
    """Remove cache 2FA"""
    try:
        if os.path.exists(get_2fa_cache_path()):
            os.remove(get_2fa_cache_path())
    except: pass


def get_wrapper_lite_2fa_path():
    configured = os.environ.get("WRAPPER_LITE_2FA_FILE", "/app/wrapper-lite-data/2fa.txt")
    return Path(configured)


def save_wrapper_lite_2fa(code):
    target = get_wrapper_lite_2fa_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="ascii", dir=target.parent, delete=False
        ) as handle:
            handle.write(f"{code}\n")
            temporary_path = Path(handle.name)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, target)
        return True
    except OSError:
        try:
            if "temporary_path" in locals():
                temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def submit_cached_2fa_if_needed():
    cached_2fa = load_2fa_cache()
    if not cached_2fa:
        return False

    deadline = time.time() + 5
    while time.time() < deadline:
        if wrapper.needs_2fa:
            wrapper.write_input(cached_2fa)
            wrapper.cached_2fa_attempt = True
            return True
        time.sleep(0.2)
    return False

# --- Rotas Principais ---

@app.route("/")
def index():
    # Tenta auto-login se tiver credenciais salvas
    creds = load_creds()
    if creds[0] and not wrapper.running:
        wrapper.start(creds[0], creds[1])
        if load_2fa_cache():
            threading.Thread(target=submit_cached_2fa_if_needed, daemon=True).start()
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
    wrapper_path = get_wrapper_bin_path()
    downloader_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'apple-music-downloader')

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
            "options": d_status["options"],
            "request_id": d_status.get("request_id")
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
@limiter.exempt
def pause_queue():
    paused = bool(request.json.get("paused"))
    return jsonify({"paused": set_pause(paused)})

@app.route("/api/cancel_task", methods=["POST"])
@limiter.exempt
def cancel_task():
    task_id = request.json.get("id")
    status = request.json.get("status")
    if status == "pending":
        cancel_pending_task(task_id)
    else:
        cancel_current_task(task_id)
    return jsonify({"status": "ok"})

@app.route("/api/move_queue", methods=["POST"])
@limiter.exempt
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
@limiter.exempt
def login_wrapper():
    email = (request.form.get("email") or "").strip()
    password = (request.form.get("password") or "").strip()
    if not email or not password:
        return jsonify({"status": "error", "message": "Credenciais inválidas."}), 400
    
    # 1. Para o processo atual
    wrapper.stop()
    time.sleep(1)
    # 2. Limpa cache antigo do wrapper em um diretório persistente, separado do binário.
    cache_dir = get_wrapper_cache_dir()
    try:
        for item in cache_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
    except FileNotFoundError:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[LOGIN WARNING] Falha ao limpar cache: {e}")

    # 3. Inicia do zero
    if wrapper.start(email, password):
        save_creds(email, password)
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})

@app.route("/stop_wrapper", methods=["POST"])
@limiter.exempt
def stop_wrapper():
    wrapper.stop()
    return jsonify({"status": "ok"})

@app.route("/reconnect_offline", methods=["POST"])
@limiter.exempt
def reconnect_offline():
    """Tenta reconectar com credenciais em cache quando internet cai"""
    creds = load_creds()
    cached_2fa = load_2fa_cache()
    
    if not creds[0] or not creds[1]:
        return jsonify({"status": "error", "message": "Sem credenciais em cache."}), 400
    
    # Para o processo atual
    wrapper.stop()
    time.sleep(0.5)
    
    # Limpa apenas o cache do wrapper em /app/config/wrapper, sem tocar no binário nem na rootfs do runtime.
    cache_dir = get_wrapper_cache_dir()
    try:
        for item in cache_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
    except FileNotFoundError:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    
    # Inicia com credenciais em cache
    if wrapper.start(creds[0], creds[1]):
        used_2fa_cache = bool(cached_2fa) and submit_cached_2fa_if_needed()
        return jsonify({"status": "ok", "used_2fa_cache": used_2fa_cache})
    return jsonify({"status": "error"})

@app.route("/submit_2fa", methods=["POST"])
@limiter.exempt
def submit_2fa():
    code = (request.form.get("twofa_code") or "").strip()
    if not code.isdigit() or len(code) != 6:
        return jsonify({"status": "error", "message": "Código 2FA inválido."}), 400
    save_2fa_cache(code)
    lite_saved = save_wrapper_lite_2fa(code)
    if wrapper.process and wrapper.process.poll() is None:
        if wrapper.write_input(code):
            return jsonify({"status": "ok", "wrapper_lite_saved": lite_saved})
        if lite_saved:
            return jsonify({"status": "ok", "wrapper_lite_saved": True})
        return jsonify({"status": "error", "message": "Wrapper não aceitou o código."}), 409
    if lite_saved:
        return jsonify({"status": "ok", "wrapper_lite_saved": True})
    return jsonify({"status": "error", "message": "Não foi possível salvar o código 2FA."}), 500

@app.route("/submit_selection", methods=["POST"])
@limiter.exempt
def submit_selection():
    sel = (request.form.get("selection") or "").strip()
    request_id = (request.form.get("selection_id") or request.form.get("request_id") or "").strip()
    if not sel:
        return jsonify({"success": False, "accepted": False, "error_code": "INVALID_SELECTION", "message": "Seleção inválida."}), 400
    
    # Suportar múltiplas seleções separadas por espaço, vírgula ou hífen (ex: "1 2 3" ou "1,2,3" ou "1-3")
    # Validar que contém apenas números, espaços, vírgulas e hífens
    if not all(c.isdigit() or c in ' ,-' for c in sel):
        return jsonify({"success": False, "accepted": False, "error_code": "INVALID_SELECTION", "message": "Seleção inválida - use números separados por espaço, vírgula ou hífen."}), 400

    if not downloader.needs_input:
        return jsonify({"success": False, "accepted": False, "error_code": "SELECTION_NOT_ACTIVE", "message": "Nenhuma seleção está aguardando confirmação."}), 409
    if request_id and request_id != downloader.selection_id:
        return jsonify({"success": False, "accepted": False, "error_code": "STALE_SELECTION", "message": "Essa seleção já não está ativa."}), 409

    available = {str(option.get("id")): option for option in downloader.input_options}
    selected_ids = []
    for token in re.split(r"[ ,]+", sel):
        if not token:
            continue
        if "-" in token:
            start, end = token.split("-", 1)
            if not start.isdigit() or not end.isdigit() or int(start) > int(end):
                return jsonify({"success": False, "accepted": False, "error_code": "INVALID_SELECTION", "message": "Intervalo de seleção inválido."}), 400
            selected_ids.extend(str(index) for index in range(int(start), int(end) + 1))
        elif token.isdigit():
            selected_ids.append(str(int(token)))
        else:
            return jsonify({"success": False, "accepted": False, "error_code": "INVALID_SELECTION", "message": "Seleção inválida."}), 400

    if not selected_ids or len(selected_ids) != len(set(selected_ids)):
        return jsonify({"success": False, "accepted": False, "error_code": "INVALID_SELECTION", "message": "Itens duplicados ou seleção vazia."}), 400
    if any(item_id not in available for item_id in selected_ids):
        return jsonify({"success": False, "accepted": False, "error_code": "INVALID_SELECTION", "message": "Um ou mais itens não pertencem à seleção atual."}), 400
    if any(available[item_id].get("selectable") is not True for item_id in selected_ids):
        return jsonify({"success": False, "accepted": False, "error_code": "UNSUPPORTED_CATEGORY", "message": "A seleção contém uma categoria não suportada."}), 400
    
    # Enviar como está para o downloader (ele entende espaços, vírgulas, ranges, etc)
    if not downloader.write_input(sel):
        return jsonify({"success": False, "accepted": False, "error_code": "PROCESS_UNAVAILABLE", "message": "O downloader não aceitou a seleção."}), 409
    return jsonify({
        "success": True,
        "accepted": True,
        "request_id": downloader.selection_id,
        "task_ids": [],
        "message": "Seleção adicionada à fila"
    })

@app.route("/skip_selection", methods=["POST"])
@limiter.exempt
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
