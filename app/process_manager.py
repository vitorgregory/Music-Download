import subprocess
import threading
import os
import re
import time
from .utils import strip_ansi, analyze_label_metadata, generate_m3u_playlist, fetch_metadata

class ProcessManager:
    def __init__(self):
        self.process = None
        self.running = False
        self.logs = []
        self.needs_input = False
        self.input_options = []
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _log(self, message):
        self.logs.append(message)
        # Mantém apenas os últimos 300 logs para economizar memória
        if len(self.logs) > 300: self.logs.pop(0)

    def stop(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                try: self.process.kill()
                except: pass
        self.running = False
        self.needs_input = False
        self._log(">>> Processo interrompido <<<")

    def write_input(self, text):
        if self.process and self.running:
            try:
                self.process.stdin.write(f"{text}\n")
                self.process.stdin.flush()
                self._log(f">>> Input enviado: {text}")
                self.needs_input = False
                return True
            except: pass
        return False

    def close_stdin(self):
        if self.process and self.running:
            try:
                self.process.stdin.close()
                self.needs_input = False
                return True
            except: pass
        return False

    def get_status(self):
        # Verifica se o processo morreu silenciosamente
        if self.process and self.process.poll() is not None:
            self.running = False
            
        return {
            "running": self.running,
            "logs": self.logs,
            "needs_input": self.needs_input,
            "options": self.input_options
        }

class WrapperManager(ProcessManager):
    def __init__(self):
        super().__init__()
        self.needs_2fa = False

    def start(self, email, password):
        if self.running: return False
        
        wrapper_path = os.path.join(self.base_dir, "wrapper", "wrapper")
        cmd = [wrapper_path, "-L", f"{email}:{password}"]
        
        try:
            env = os.environ.copy()
            env["TERM"] = "dumb"
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                stdin=subprocess.PIPE, bufsize=1, universal_newlines=True, 
                cwd=os.path.dirname(wrapper_path), env=env
            )
            self.running = True
            self.needs_2fa = False
            self.logs = ["Iniciando Wrapper..."]
            threading.Thread(target=self._stream_logs, daemon=True).start()
            return True
        except Exception as e:
            self._log(f"Erro Wrapper: {e}")
            return False

    def _stream_logs(self):
        try:
            for line in iter(self.process.stdout.readline, ''):
                line = line.strip()
                if not line: continue
                clean = strip_ansi(line)
                self.logs.append(line)
                
                # Detectores de Estado
                if "credentialhandler" in clean.lower() and "2fa" in clean.lower():
                    self.needs_2fa = True
                    self.logs.append(">>> 2FA NECESSÁRIO - Digite o código <<<")
                
                if "response type 6" in clean.lower() or "success" in clean.lower():
                    self.needs_2fa = False
        finally:
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
            env = os.environ.copy()
            env["TERM"] = "dumb"
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                stdin=subprocess.PIPE, bufsize=1, universal_newlines=True, 
                cwd=amd_dir, env=env
            )
            self.running = True
            self.needs_input = False
            self.input_options = []
            self.logs = [f"Iniciando: {link}"]
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
            for line in iter(self.process.stdout.readline, ''):
                line = line.strip()
                if not line: continue
                
                self.logs.append(line)
                log_buffer.append(line)
                clean_line = strip_ansi(line).lower()
                
                # Detecção de Input
                if any(k in clean_line for k in self.selection_keywords):
                    self.input_options = self._parse_options(log_buffer)
                    if self.input_options:
                        self.needs_input = True
                        self.logs.append(">>> AGUARDANDO SELEÇÃO DO USUÁRIO <<<")
        finally:
            self.running = False
            if self.is_playlist:
                time.sleep(1)
                generate_m3u_playlist(self.current_format)

wrapper = WrapperManager()
downloader = DownloaderManager()
