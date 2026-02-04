import sqlite3
import threading
import time
import os
import re
from datetime import datetime, timedelta
from .process_manager import downloader
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "queue.db")
QUEUE_PAUSED = False
STALL_TIMEOUT_SECONDS = int(os.environ.get('STALL_TIMEOUT_SECONDS', 300))

# Worker control (allow tests to disable auto-start)
WORKER_THREAD = None
WORKER_STOP_EVENT = threading.Event()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db_connection()
    c = conn.cursor()
    # The queue table includes scheduling columns used by the retry/backoff system.
    # We create the columns here (and below attempt non-destructive ALTERs) so
    # existing databases are migrated automatically on startup where possible.
    c.execute('''CREATE TABLE IF NOT EXISTS queue 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  link TEXT, format TEXT, status TEXT, title TEXT, 
                  progress TEXT, created_at TIMESTAMP, position INTEGER,
                  failed_attempts INTEGER DEFAULT 0, next_try_at TIMESTAMP NULL)''')
    # Backwards-compatible migrations
    try: c.execute("ALTER TABLE queue ADD COLUMN failed_attempts INTEGER DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE queue ADD COLUMN next_try_at TIMESTAMP NULL")
    except: pass
    c.execute("CREATE INDEX IF NOT EXISTS idx_status ON queue(status)")
    c.execute("UPDATE queue SET status = 'failed', progress = 'Reiniciado' WHERE status = 'processing'")
    c.execute("UPDATE queue SET position = id WHERE position IS NULL")
    conn.commit()
    conn.close()

def add_to_queue(link, fmt, title=None):
    conn = get_db_connection()
    safe_title = title if title else "Aguardando metadados..."
    max_position = conn.execute("SELECT COALESCE(MAX(position), 0) FROM queue").fetchone()[0]
    next_position = max_position + 1
    conn.execute(
        "INSERT INTO queue (link, format, status, title, progress, created_at, position, failed_attempts, next_try_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (link, fmt, "pending", safe_title, "0", datetime.now(), next_position, 0, None)
    )
    conn.commit()
    conn.close()

def get_queue_status():
    conn = get_db_connection()
    items = conn.execute("SELECT * FROM queue ORDER BY position ASC, id DESC").fetchall()
    conn.close()
    return {"items": [dict(ix) for ix in items], "paused": QUEUE_PAUSED}

def set_pause(paused):
    global QUEUE_PAUSED
    QUEUE_PAUSED = paused
    return QUEUE_PAUSED

def cancel_current_task(task_id):
    if downloader.running:
        downloader.stop()
    update_status(task_id, "cancelled", progress="Cancelado pelo usuário")

def cancel_pending_task(task_id):
    update_status(task_id, "cancelled", progress="Cancelado pelo usuário")

def swap_queue_positions(first_id, second_id):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, position FROM queue WHERE id IN (?, ?)", (first_id, second_id)
    ).fetchall()
    if len(rows) != 2:
        conn.close()
        return False
    pos_map = {row["id"]: row["position"] for row in rows}
    conn.execute("UPDATE queue SET position = ? WHERE id = ?", (pos_map[first_id], second_id))
    conn.execute("UPDATE queue SET position = ? WHERE id = ?", (pos_map[second_id], first_id))
    conn.commit()
    conn.close()
    return True

def move_queue_item(task_id, direction):
    conn = get_db_connection()
    item = conn.execute(
        "SELECT id, position FROM queue WHERE id = ? AND status = 'pending'", (task_id,)
    ).fetchone()
    if not item:
        conn.close()
        return False
    operator = "<" if direction == "up" else ">"
    order = "DESC" if direction == "up" else "ASC"
    neighbor = conn.execute(
        f"SELECT id, position FROM queue WHERE status = 'pending' AND position {operator} ? ORDER BY position {order} LIMIT 1",
        (item["position"],)
    ).fetchone()
    conn.close()
    if not neighbor:
        return False
    return swap_queue_positions(item["id"], neighbor["id"])

def update_status(task_id, status, title=None, progress=None):
    conn = get_db_connection()
    query = "UPDATE queue SET status = ?"
    params = [status]
    if title:
        query += ", title = ?"
        params.append(title)
    if progress:
        query += ", progress = ?"
        params.append(progress)
    query += " WHERE id = ?"
    params.append(task_id)
    conn.execute(query, tuple(params))
    conn.commit()
    conn.close()

def extract_percentage(logs):
    if not logs: return None
    for line in reversed(logs[-10:]):
        match = re.search(r'(\d{1,3})%', line)
        if match: return match.group(1)
    return None

def find_error_in_logs(logs):
    """Analisa logs procurando o motivo real da falha"""
    if not logs: return "Erro desconhecido"
    
    # Procura do fim para o começo
    for line in reversed(logs[-50:]):
        l = line.lower()
        
        # Erros Críticos de DRM/Codec
        if "no codec found" in l: return "Erro DRM: Codec não encontrado (Relogar)"
        if "failed to extract" in l: return "Falha na extração"
        if "unauthorized" in l or "401" in l: return "Erro 401: Token Expirado"
        if "geo restricted" in l: return "Bloqueio de Região"
        
        # Erros Genéricos
        if "error" in l or "failed" in l or "panic" in l:
            return line[-40:] # Retorna pedaço do erro
            
    return "Falha no processo"


def locate_existing_file(task_id):
    """Tenta localizar um arquivo existente no diretório `downloads` usando `title` da tarefa."""
    try:
        conn = get_db_connection()
        row = conn.execute("SELECT title FROM queue WHERE id = ?", (task_id,)).fetchone()
        conn.close()
        if not row or not row['title']:
            return None
        title = row['title']
        # candidate tokens (ignore short tokens)
        tokens = [t for t in re.split(r'[^a-z0-9]+', title.lower()) if len(t) > 2]
        if not tokens:
            return None
        # search downloads dir
        downloads_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'downloads'))
        if not os.path.exists(downloads_path):
            return None
        for root, dirs, files in os.walk(downloads_path):
            for f in files:
                low = f.lower()
                if all(tok in low for tok in tokens[:2]):
                    return os.path.join(root, f)
                # fallback: any token match
                if any(tok in low for tok in tokens):
                    return os.path.join(root, f)
    except Exception:
        return None
    return None

def queue_worker():
    print("[SYSTEM] Queue Worker V3.3 (Error Detection) Iniciado")
    init_db()
    
    while not WORKER_STOP_EVENT.is_set():
        try:
            if QUEUE_PAUSED or downloader.running:
                # Sleep but wake early if stop requested
                for _ in range(10):
                    if WORKER_STOP_EVENT.is_set(): break
                    time.sleep(0.1)
                continue

            conn = get_db_connection()
            now = datetime.now()
            # Only select tasks that are pending and whose `next_try_at` is either NULL
            # (never tried) or scheduled to run now/past. This ensures exponential backoff
            # scheduling is respected and we don't pick tasks that are waiting for retry.
            task = conn.execute("SELECT * FROM queue WHERE status = 'pending' AND (next_try_at IS NULL OR next_try_at <= ?) ORDER BY position ASC, id ASC LIMIT 1", (now,)).fetchone()
            conn.close()

            if not task:
                for _ in range(20):
                    if WORKER_STOP_EVENT.is_set(): break
                    time.sleep(0.1)
                continue

            current_id = task['id']
            link = task['link']
            
            if not link or str(link).lower() == "null":
                update_status(current_id, "failed", progress="Link Inválido")
                continue

            print(f"[QUEUE] Iniciando Tarefa #{current_id}")
            update_status(current_id, "processing", progress="0")
            
            args = []
            if task['format'] == "atmos": args = ["--atmos"]
            elif task['format'] == "aac": args = ["--aac"]
            
            if downloader.start(link, args):
                last_perc = "0"
                has_critical_error = False
                stall_detected = False
                
                # Main processing loop: wait until downloader stops
                while downloader.running:
                    # Real-time critical error monitoring
                    # If "no codec found" appears, we know it will fail
                    if not has_critical_error:
                        for line in downloader.logs[-5:]:
                            if "no codec found" in line.lower():
                                has_critical_error = True
                    
                    # Extract and update progress percentage
                    new_perc = extract_percentage(downloader.logs)
                    if new_perc:
                        last_perc = new_perc
                        update_status(current_id, "processing", progress=new_perc)

                    # Detect stalled task: no output for configured timeout
                    try:
                        if getattr(downloader, 'last_output_at', None) is not None:
                            if time.time() - downloader.last_output_at > STALL_TIMEOUT_SECONDS:
                                stall_detected = True
                                print(f"[QUEUE] Detected stall for task #{current_id} (no output for {STALL_TIMEOUT_SECONDS}s)")
                                downloader.stop()
                                break
                    except Exception:
                        pass
                    
                    # Sleep in small increments to allow quick response to stop event
                    for _ in range(10):
                        if WORKER_STOP_EVENT.is_set(): break
                        time.sleep(0.1)
                
                # --- POST-COMPLETION ANALYSIS ---
                # Check if task was cancelled by user
                conn_check = get_db_connection()
                db_state = conn_check.execute("SELECT status FROM queue WHERE id = ?", (current_id,)).fetchone()
                conn_check.close()

                if db_state and db_state['status'] == "cancelled":
                    continue

                # If stall was detected, mark as failure
                if stall_detected:
                    _handle_failure(current_id, f"Tarefa travada: sem saída por {STALL_TIMEOUT_SECONDS}s")
                    continue

                # Determine if download succeeded or failed
                # Priority: 1) process exit code, 2) is_complete() check, 3) percentage & logs
                process_exit_ok = (downloader.process and downloader.process.poll() == 0)
                is_truly_complete = downloader.is_complete()
                
                # Final percentage fallback
                final_perc = extract_percentage(downloader.logs)
                if final_perc:
                    last_perc = final_perc
                
                # SUCCESS: process exited cleanly (0) OR is_complete() detected completion pattern
                if process_exit_ok or (is_truly_complete and last_perc == "100"):
                    update_status(current_id, "completed", progress="100")
                # SPECIAL CASE: track already exists locally
                elif "already exists" in "\n".join(downloader.logs[-50:]).lower():
                    path = locate_existing_file(current_id)
                    if path:
                        print(f"[QUEUE] Track exists locally: {path}")
                        update_status(current_id, 'completed', progress=f"Exists at {path}")
                    else:
                        print("[QUEUE] Track exists but file not found on disk")
                        _handle_failure(current_id, 'Exists locally (not found)')
                # FAILURE: analyze and decide retry vs dead-letter
                else:
                    error_msg = find_error_in_logs(downloader.logs)
                    print(f"[QUEUE] Task #{current_id} failed: {error_msg}")
                    _handle_failure(current_id, error_msg)
            else:
                # Failed to start the downloader process - transient error, will retry
                _handle_failure(current_id, "Falha ao iniciar")
            
        except Exception as e:
            print(f"[QUEUE ERROR] {e}")
            for _ in range(50):
                if WORKER_STOP_EVENT.is_set(): break
                time.sleep(0.1)


def start_worker():
    global WORKER_THREAD
    if WORKER_THREAD and WORKER_THREAD.is_alive():
        return WORKER_THREAD
    WORKER_STOP_EVENT.clear()
    WORKER_THREAD = threading.Thread(target=queue_worker, daemon=True)
    WORKER_THREAD.start()
    return WORKER_THREAD


# Auto-start unless explicitly disabled (useful for tests)
if os.environ.get('DISABLE_QUEUE_WORKER') != '1':
    start_worker()


def _is_permanent_error(msg: str) -> bool:
    if not msg: return False
    l = msg.lower()
    if 'drm' in l or '401' in l or 'unauthorized' in l or 'geo restricted' in l:
        return True
    return False


def _handle_failure(task_id: int, error_msg: str, max_retries: Optional[int] = None, base_seconds: Optional[int] = None):
    """Decide whether to retry a failed task or move it to dead-letter.

    Behavior summary:
    - If the error looks permanent (DRM/401/unauthorized) or the task has reached
      `max_retries`, mark it as `dead` with the error message stored in `progress`.
    - Otherwise, increment `failed_attempts` and set `next_try_at` using exponential
      backoff: `base_seconds * (2 ** (attempts-1))`. The worker will skip tasks
      until `next_try_at` is reached.
    """
    try:
        max_retries = int(os.environ.get('MAX_RETRIES', 3)) if max_retries is None else max_retries
        base_seconds = int(os.environ.get('RETRY_BASE_SECONDS', 5)) if base_seconds is None else base_seconds

        conn = get_db_connection()
        row = conn.execute("SELECT failed_attempts FROM queue WHERE id = ?", (task_id,)).fetchone()
        attempts = row['failed_attempts'] if row else 0

        # Permanent error -> dead-letter
        if _is_permanent_error(error_msg) or attempts >= max_retries:
            conn.execute("UPDATE queue SET status = ?, progress = ?, failed_attempts = ? WHERE id = ?", ('dead', error_msg, attempts + 1, task_id))
            conn.commit()
            conn.close()
            print(f"[QUEUE] Task #{task_id} moved to dead-letter: {error_msg}")
            return

        # Transient: schedule retry with exponential backoff
        attempts += 1
        backoff = base_seconds * (2 ** (attempts - 1))
        next_try = datetime.now() + timedelta(seconds=backoff)
        conn.execute("UPDATE queue SET status = ?, progress = ?, failed_attempts = ?, next_try_at = ? WHERE id = ?",
                     ('pending', f"Retry in {backoff}s", attempts, next_try, task_id))
        conn.commit()
        conn.close()
        print(f"[QUEUE] Task #{task_id} scheduled to retry in {backoff}s (attempt {attempts}/{max_retries})")
    except Exception as e:
        print(f"[QUEUE] Error handling failure for task {task_id}: {e}")
