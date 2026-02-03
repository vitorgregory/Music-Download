import sqlite3
import threading
import time
import os
import re
from datetime import datetime
from .process_manager import downloader

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "queue.db")
QUEUE_PAUSED = False

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS queue 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  link TEXT, format TEXT, status TEXT, title TEXT, 
                  progress TEXT, created_at TIMESTAMP, position INTEGER)''')
    try: c.execute("ALTER TABLE queue ADD COLUMN progress TEXT")
    except: pass
    try: c.execute("ALTER TABLE queue ADD COLUMN position INTEGER")
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
        "INSERT INTO queue (link, format, status, title, progress, created_at, position) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (link, fmt, "pending", safe_title, "0", datetime.now(), next_position)
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

def queue_worker():
    print("[SYSTEM] Queue Worker V3.3 (Error Detection) Iniciado")
    init_db()
    
    while True:
        try:
            if QUEUE_PAUSED or downloader.running:
                time.sleep(1)
                continue

            conn = get_db_connection()
            task = conn.execute("SELECT * FROM queue WHERE status = 'pending' ORDER BY id ASC LIMIT 1").fetchone()
            conn.close()

            if not task:
                time.sleep(2)
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
                
                while downloader.running:
                    # Monitoramento em tempo real de erros críticos
                    # Se aparecer "no codec found" enquanto roda, já sabemos que vai falhar
                    if not has_critical_error:
                         for line in downloader.logs[-5:]:
                             if "no codec found" in line.lower():
                                 has_critical_error = True
                    
                    new_perc = extract_percentage(downloader.logs)
                    if new_perc:
                        last_perc = new_perc
                        update_status(current_id, "processing", progress=new_perc)
                    
                    time.sleep(1)
                
                # --- ANÁLISE PÓS-MORTE ---
                conn_check = get_db_connection()
                db_state = conn_check.execute("SELECT status FROM queue WHERE id = ?", (current_id,)).fetchone()
                conn_check.close()

                if db_state and db_state['status'] == "cancelled":
                    continue

                # Sucesso APENAS se chegou em 100% E não teve erro crítico detectado
                if last_perc == "100" and not has_critical_error:
                    update_status(current_id, "completed", progress="100")
                else:
                    # Falhou
                    error_msg = find_error_in_logs(downloader.logs)
                    print(f"[QUEUE] Falha marcada: {error_msg}")
                    update_status(current_id, "failed", progress=error_msg)
            else:
                update_status(current_id, "failed", progress="Falha ao iniciar")
            
        except Exception as e:
            print(f"[QUEUE ERROR] {e}")
            time.sleep(5)

threading.Thread(target=queue_worker, daemon=True).start()
