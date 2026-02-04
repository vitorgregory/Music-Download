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
    # Convert deque to list for slicing
    log_list = list(logs) if hasattr(logs, '__iter__') else logs
    for line in reversed(log_list[-10:]):
        match = re.search(r'(\d{1,3})%', line)
        if match: return match.group(1)
    return None

def find_error_in_logs(logs):
    """Analisa logs procurando o motivo real da falha"""
    if not logs: return "Erro desconhecido"
    
    # Convert deque to list for slicing
    log_list = list(logs) if hasattr(logs, '__iter__') else logs
    
    # Procura do fim para o começo
    for line in reversed(log_list[-50:]):
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
    """
    Simple, reliable queue worker.
    - Pick next pending task
    - Start downloader process
    - Wait for process to complete
    - Check exit code immediately
    - Mark complete or handle failure
    """
    print("[SYSTEM] Queue Worker V4 (Rewritten) Iniciado")
    init_db()
    
    while not WORKER_STOP_EVENT.is_set():
        try:
            # Skip if paused or already processing
            if QUEUE_PAUSED:
                for _ in range(20):
                    if WORKER_STOP_EVENT.is_set(): break
                    time.sleep(0.1)
                continue
            
            # Wait if downloader is busy
            if downloader.running:
                for _ in range(10):
                    if WORKER_STOP_EVENT.is_set(): break
                    time.sleep(0.1)
                continue

            # Pick next pending task
            conn = get_db_connection()
            now = datetime.now()
            task = conn.execute(
                "SELECT * FROM queue WHERE status = 'pending' AND (next_try_at IS NULL OR next_try_at <= ?) ORDER BY position ASC, id ASC LIMIT 1",
                (now,)
            ).fetchone()
            conn.close()

            if not task:
                # No pending tasks, sleep
                for _ in range(20):
                    if WORKER_STOP_EVENT.is_set(): break
                    time.sleep(0.1)
                continue

            current_id = task['id']
            link = task['link']
            
            if not link or str(link).lower() == "null":
                update_status(current_id, "failed", progress="Link Inválido")
                continue

            # Start download
            print(f"[QUEUE] Task #{current_id}: Starting download")
            update_status(current_id, "processing", progress="0")
            
            args = []
            if task['format'] == "atmos":
                args = ["--atmos"]
            elif task['format'] == "aac":
                args = ["--aac"]
            
            if not downloader.start(link, args):
                print(f"[QUEUE] Task #{current_id}: Failed to start downloader")
                _handle_failure(current_id, "Falha ao iniciar")
                continue

            # SIMPLE LOOP: Just monitor progress and stalls
            # Exit when: process completes, stall detected, or user cancels
            stall_detected = False
            last_perc = "0"
            
            while True:
                # Check if process still running
                if not downloader.process or downloader.process.poll() is not None:
                    # Process exited!
                    break
                
                # Check if user cancelled
                conn_check = get_db_connection()
                db_status = conn_check.execute("SELECT status FROM queue WHERE id = ?", (current_id,)).fetchone()
                conn_check.close()
                if db_status and db_status['status'] == "cancelled":
                    print(f"[QUEUE] Task #{current_id}: Cancelled by user")
                    break
                
                # Update progress
                new_perc = extract_percentage(downloader.logs)
                if new_perc and new_perc != last_perc:
                    last_perc = new_perc
                    update_status(current_id, "processing", progress=new_perc)
                
                # Check for stall (no output for N seconds)
                if hasattr(downloader, 'last_output_at') and downloader.last_output_at:
                    elapsed = time.time() - downloader.last_output_at
                    if elapsed > STALL_TIMEOUT_SECONDS:
                        print(f"[QUEUE] Task #{current_id}: Stalled (no output for {int(elapsed)}s)")
                        stall_detected = True
                        downloader.stop()
                        break
                
                # Brief sleep
                time.sleep(0.5)

            # TASK COMPLETE - Determine outcome
            print(f"[QUEUE] Task #{current_id}: Process exited, analyzing result...")
            
            # Check if user cancelled
            conn_check = get_db_connection()
            db_status = conn_check.execute("SELECT status FROM queue WHERE id = ?", (current_id,)).fetchone()
            conn_check.close()
            if db_status and db_status['status'] == "cancelled":
                print(f"[QUEUE] Task #{current_id}: Skipping (already cancelled)")
                continue
            
            # If stall was detected
            if stall_detected:
                print(f"[QUEUE] Task #{current_id}: Marked as stalled failure")
                _handle_failure(current_id, f"Tarefa travada (sem saída por {STALL_TIMEOUT_SECONDS}s)")
                continue
            
            # Get final exit code
            exit_code = downloader.process.returncode if downloader.process else -1
            print(f"[QUEUE] Task #{current_id}: Exit code = {exit_code}")
            
            # SUCCESS if exit code is 0
            if exit_code == 0:
                print(f"[QUEUE] Task #{current_id}: COMPLETED ✓")
                update_status(current_id, "completed", progress="100")
                continue
            
            # Check for "already exists" case
            log_text = "\n".join(downloader.logs[-50:]).lower()
            if "already exists" in log_text or "track already exists" in log_text:
                path = locate_existing_file(current_id)
                if path:
                    print(f"[QUEUE] Task #{current_id}: Track exists at {path}")
                    update_status(current_id, 'completed', progress=f"Exists at {path}")
                else:
                    print(f"[QUEUE] Task #{current_id}: Track exists but file not found")
                    _handle_failure(current_id, 'Exists locally (not found)')
                continue
            
            # FAILURE: Analyze error
            error_msg = find_error_in_logs(downloader.logs)
            print(f"[QUEUE] Task #{current_id}: FAILED - {error_msg}")
            _handle_failure(current_id, error_msg)
            
        except Exception as e:
            import traceback
            print(f"[QUEUE ERROR] {e}")
            traceback.print_exc()
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
