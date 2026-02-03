import subprocess
import threading
import os
import re
import time
import platform
import signal
from collections import deque
from .utils import strip_ansi, analyze_label_metadata, generate_m3u_playlist, fetch_metadata

class ProcessManager:
    def __init__(self):
        self.process = None
        self.running = False
        self.logs = deque(maxlen=300)
        self.needs_input = False
        self.input_options = []
        self._lock = threading.Lock()
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _log(self, message):
        with self._lock:
            self.logs.append(message)

    def stop(self):
        if self.process:
            try:
                # Try graceful termination first
                try:
                    self.process.terminate()
                except Exception:
                    pass
                try:
                    self.process.wait(timeout=2)
                except Exception:
                    # On Windows try CTRL_BREAK for process group if created
                    if platform.system() == 'Windows':
                        try:
                            self.process.send_signal(signal.CTRL_BREAK_EVENT)
                        except Exception:
                            pass
                    try:
                        self.process.kill()
                    except Exception:
                        pass
            except:
                pass
        with self._lock:
            self.running = False
            self.needs_input = False
        self._log(">>> Processo interrompido <<<")

    def write_input(self, text):
        with self._lock:
            proc = self.process
            running = self.running
        if proc and running:
            try:
                proc.stdin.write(f"{text}\n")
                proc.stdin.flush()
                self._log(f">>> Input enviado: {text}")
                with self._lock:
                    self.needs_input = False
                return True
            except Exception:
                return False
        return False

    def close_stdin(self):
        with self._lock:
            proc = self.process
            running = self.running
        if proc and running:
            try:
                proc.stdin.close()
                with self._lock:
                    self.needs_input = False
                return True
            except Exception:
                return False
        return False

    def get_status(self):
        # Verifica se o processo morreu silenciosamente
        with self._lock:
            if self.process and self.process.poll() is not None:
                self.running = False
            return {
                "running": self.running,
                "logs": list(self.logs),
                "needs_input": self.needs_input,
                "options": self.input_options,
                "last_output_at": getattr(self, 'last_output_at', None)
            }

class WrapperManager(ProcessManager):
    def __init__(self):
        super().__init__()
        self.last_output_at = None
        self.needs_2fa = False

    def start(self, email, password):
        if self.running: return False
        
        wrapper_path = os.path.join(self.base_dir, "wrapper", "wrapper")
        # Verify wrapper binary exists
        if not os.path.exists(wrapper_path):
            self._log(f"Erro Wrapper: binary not found at {wrapper_path}")
            return False
        cmd = [wrapper_path, "-L", f"{email}:{password}"]
        
        try:
            env = os.environ.copy()
            env["TERM"] = "dumb"
            kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          stdin=subprocess.PIPE, bufsize=1, universal_newlines=True,
                          cwd=os.path.dirname(wrapper_path), env=env)
            if platform.system() == 'Windows':
                kwargs.update(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                kwargs.update(preexec_fn=os.setsid)
            self.process = subprocess.Popen(cmd, **kwargs)
            with self._lock:
                self.running = True
                self.needs_2fa = False
                self.logs.clear()
                self.logs.append("Iniciando Wrapper...")
            threading.Thread(target=self._stream_logs, daemon=True).start()
            return True
        except Exception as e:
            self._log(f"Erro Wrapper: {e}")
            return False

    def _stream_logs(self):
        try:
            while True:
                if not self.process:
                    break
                line = self.process.stdout.readline()
                if line == '' or line is None:
                    break
                line = line.strip()
                if not line:
                    if self.process.poll() is not None:
                        break
                    continue
                clean = strip_ansi(line)
                self._log(line)
                # Detectores de Estado
                if "credentialhandler" in clean.lower() and "2fa" in clean.lower():
                    with self._lock:
                        self.needs_2fa = True
                    self._log(">>> 2FA NECESSÁRIO - Digite o código <<<")
                if "response type 6" in clean.lower() or "success" in clean.lower():
                    with self._lock:
                        self.needs_2fa = False
        finally:
            with self._lock:
                self.running = False

class DownloaderManager(ProcessManager):
    def __init__(self):
        super().__init__()
        # Pré-compila Regex para performance
        self.re_table = re.compile(r"^\s*\|\s*(\d+)\s*\|")
        self.re_list = re.compile(r"(?:^|\s|\[\w+\]\s+)(\d+)\s*[\.\:\-\)\]]\s+(.+)$")
        self.selection_keywords = ["select:", "enter choice", "choice:", "selection:"]
        self.re_date = re.compile(r"\b(\d{4}([-/.]\d{2}([-/.]\d{2})?)?)\b")
        self.re_duration = re.compile(r"\b(\d{1,2}:\d{2})\b")

    def _split_table_row(self, clean):
        if "|" not in clean:
            return None
        cells = [c.strip() for c in clean.strip().strip("|").split("|")]
        if not cells or not cells[0].isdigit():
            return None
        return cells

    def _extract_table_metadata(self, cells):
        entry_id = cells[0]
        columns = cells[1:]
        if not columns:
            return None

        label = columns[0]
        date = ""
        kind = ""
        duration = ""
        extras = []

        for col in columns[1:]:
            if not date and self.re_date.search(col):
                date = col.strip()
                continue
            if not duration and self.re_duration.search(col):
                duration = col.strip()
                continue
            if not kind and any(t in col.lower() for t in ["album", "single", "ep", "video"]):
                kind = col.strip()
                continue
            extras.append(col.strip())

        meta = analyze_label_metadata(label)
        if kind:
            meta["type"] = kind
        return {
            "id": entry_id,
            "label": meta["label"],
            "type": meta["type"],
            "tags": meta["tags"],
            "date": date,
            "duration": duration,
            "extra": ", ".join([e for e in extras if e])
        }

    def start(self, link, args=None):
        if self.running: return False
        
        amd_dir = os.path.join(self.base_dir, "apple-music-downloader")
        # Ensure the Go project folder exists before attempting to run it
        if not os.path.isdir(amd_dir):
            self._log(f"Erro Downloader: apple-music-downloader folder not found at {amd_dir}")
            return False

        cmd = ["go", "run", "main.go"]
        self.current_format = "alac"
        
        if args: 
            cmd.extend(args)
            if "--atmos" in args: self.current_format = "atmos"
            elif "--aac" in args: self.current_format = "aac"
            
        cmd.append(link)
        
        # Check Playlist
        self.is_playlist = False
        try:
            meta = fetch_metadata(link)
            if meta and meta.get('type') == 'Playlist':
                self.is_playlist = True
        except: pass
        
        try:
            # Ensure diagnostic log exists and reset it at start
            try:
                data_dir = os.path.join(self.base_dir, "data")
                os.makedirs(data_dir, exist_ok=True)
                with open(os.path.join(data_dir, "current_task.log"), "w", encoding="utf-8") as f:
                    f.write(f"--- Starting download: {link} at {time.ctime()} ---\n")
            except Exception:
                pass

            # initialize last_output_at to now so the stall detector has a baseline
            try:
                self.last_output_at = time.time()
            except Exception:
                pass
            env = os.environ.copy()
            env["TERM"] = "dumb"
            kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          stdin=subprocess.PIPE, bufsize=1, universal_newlines=True,
                          cwd=amd_dir, env=env)
            if platform.system() == 'Windows':
                kwargs.update(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                kwargs.update(preexec_fn=os.setsid)
            self.process = subprocess.Popen(cmd, **kwargs)
            with self._lock:
                self.running = True
                self.needs_input = False
                self.input_options = []
                self.logs.clear()
                self.logs.append(f"Iniciando: {link}")
            threading.Thread(target=self._stream_logs, daemon=True).start()
            return True
        except Exception as e:
            self._log(f"Erro Downloader: {e}")
            return False

    def _parse_options(self, buffer):
        options = []
        # Analisa os últimos logs em busca de tabelas ou listas
        for line in reversed(buffer[-50:]):
            clean = strip_ansi(line).strip()
            if not clean or any(k in clean.lower() for k in self.selection_keywords): continue
            if "+---" in clean or "ALBUM NAME" in clean: continue
            
            # Tenta Tabela
            m = self.re_table.search(clean)
            if m:
                cells = self._split_table_row(clean)
                parsed = self._extract_table_metadata(cells) if cells else None
                if parsed:
                    options.insert(0, parsed)
                continue
            
            # Tenta Lista
            m = self.re_list.search(clean)
            if m:
                meta = analyze_label_metadata(m.group(2).strip())
                options.insert(0, {
                    "id": m.group(1), "label": meta['label'], "type": meta['type'], 
                    "tags": meta['tags'], "date": "", "duration": "", "extra": ""
                })
        return options

    def _stream_logs(self):
        log_buffer = []
        try:
            while True:
                if not self.process:
                    break
                line = self.process.stdout.readline()
                if line == '' or line is None:
                    break
                line = line.strip()
                if not line:
                    if self.process.poll() is not None:
                        break
                    continue

                # record timestamp of last output and persist raw line for diagnostics
                try:
                    self.last_output_at = time.time()
                    data_dir = os.path.join(self.base_dir, "data")
                    os.makedirs(data_dir, exist_ok=True)
                    with open(os.path.join(data_dir, "current_task.log"), "a", encoding="utf-8") as f:
                        f.write(line + "\n")
                except Exception:
                    # best-effort only; never crash the log loop
                    pass

                self._log(line)
                log_buffer.append(line)
                clean_line = strip_ansi(line).lower()

                # Detecção de Input
                if any(k in clean_line for k in self.selection_keywords):
                    options = self._parse_options(log_buffer)
                    if options:
                        with self._lock:
                            self.input_options = options
                            self.needs_input = True
                        self._log(">>> AGUARDANDO SELEÇÃO DO USUÁRIO <<<")
        finally:
            with self._lock:
                self.running = False
            if self.is_playlist:
                time.sleep(1)
                generate_m3u_playlist(self.current_format)

wrapper = WrapperManager()
downloader = DownloaderManager()
