import subprocess
import threading
import os
import re
import time
# Adicionei fetch_metadata na importação
from .utils import strip_ansi, analyze_label_metadata, generate_m3u_playlist, fetch_metadata

class ProcessManager:
    """Classe base para gerenciar processos em background"""
    def __init__(self):
        self.process = None
        self.running = False
        self.logs = []
        self.needs_input = False
        self.input_options = []
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _log(self, message):
        self.logs.append(message)
        print(message)

    def stop(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                self.process.kill()
        self.running = False
        self.needs_input = False
        self._log(">>> Processo encerrado <<<")

    def write_input(self, text):
        if self.process and self.running:
            try:
                self.process.stdin.write(f"{text}\n")
                self.process.stdin.flush()
                self._log(f">>> Input enviado: {text}")
                self.needs_input = False
                return True
            except Exception as e:
                self._log(f"Erro ao enviar input: {e}")
        return False

    def close_stdin(self):
        if self.process and self.running:
            try:
                self.process.stdin.close()
                self._log(">>> Input encerrado (Skip) <<<")
                self.needs_input = False
                return True
            except: pass
        return False

    def get_status(self):
        if self.process and self.process.poll() is not None:
            self.running = False
        return {
            "running": self.running,
            "logs": self.logs[-200:],
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
            self.logs = [] 
            
            threading.Thread(target=self._stream_logs, daemon=True).start()
            return True
        except Exception as e:
            self._log(f"Erro ao iniciar Wrapper: {e}")
            return False

    def _stream_logs(self):
        try:
            for line in iter(self.process.stdout.readline, ''):
                line = line.strip()
                if not line: continue
                
                clean = strip_ansi(line)
                self.logs.append(line)
                print(f"[WRAPPER] {line}")

                if "credentialhandler" in clean.lower() and "2fa" in clean.lower():
                    self.needs_2fa = True
                    self.logs.append(">>> 2FA SOLICITADO <<<")
                
                if "[.] response type 6" in clean:
                    self.needs_2fa = False
                    self.logs.append(">>> LOGIN COM SUCESSO <<<")
        finally:
            self.running = False

class DownloaderManager(ProcessManager):
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
        
        # --- NOVO: Detecta se é playlist ANTES de começar ---
        self.is_playlist = False
        try:
            meta = fetch_metadata(link)
            if meta and meta.get('type') == 'Playlist':
                self.is_playlist = True
                print("[INFO] Conteúdo identificado como Playlist. Arquivo m3u8 será gerado.")
            else:
                print(f"[INFO] Conteúdo identificado como {meta.get('type') if meta else 'Desconhecido'}. Pular geração de m3u8.")
        except:
            pass
        
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
            self.logs = [f"Iniciando download: {link}"]
            
            threading.Thread(target=self._stream_logs, daemon=True).start()
            return True
        except Exception as e:
            self._log(f"Erro ao iniciar Downloader: {e}")
            return False

    def _stream_logs(self):
        selection_keywords = ["Select:", "Enter choice", "Input:", "(default: All)", "Choice:", "selection:", "Select options"]
        log_buffer = []

        def parse_options(buffer):
            options = []
            # Regex tabela: Pega o ID, Nome e Data
            regex_table = r"^\s*\|\s*(\d+)\s*\|\s*([^\|]+)\s*\|\s*([^\|]+)"
            # Regex lista simples (raramente tem data, mas tratamos)
            regex_list = r"(?:^|\s|\[\w+\]\s+)(\d+)\s*[\.\:\-\)\]]\s+(.+)$"
            
            for line in reversed(buffer[-200:]):
                clean = strip_ansi(line).strip()
                if not clean or any(k.lower() in clean.lower() for k in selection_keywords): continue
                if "+---" in clean or "ALBUM NAME" in clean: continue
                
                # Tenta Tabela (com Data)
                m = re.search(regex_table, clean)
                if m:
                    # m.group(2) é o nome, m.group(3) é a data (Ano-Mes-Dia)
                    meta = analyze_label_metadata(m.group(2).strip())
                    options.insert(0, {
                        "id": m.group(1), 
                        "label": meta['label'], 
                        "type": meta['type'], 
                        "tags": meta['tags'], 
                        "date": m.group(3).strip() # Passa a data bruta para o frontend
                    })
                    continue
                
                # Tenta Lista Simples
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

        buffer_str = ""
        try:
            while True:
                char = self.process.stdout.read(1)
                if not char: break
                buffer_str += char
                
                is_newline = char == '\n'
                is_prompt = len(buffer_str) > 300 or buffer_str.endswith(": ") or buffer_str.endswith("? ")
                
                if is_newline or is_prompt:
                    line = buffer_str.strip()
                    if line:
                        self.logs.append(line)
                        print(f"[DL] {line}")
                        log_buffer.append(line)
                        
                        clean_line = strip_ansi(line)
                        if any(k.lower() in clean_line.lower() for k in selection_keywords):
                            opts = parse_options(log_buffer)
                            self.input_options = opts
                            self.needs_input = True
                            self.logs.append(">>> AGUARDANDO INTERAÇÃO <<<")
                    
                    if is_newline: buffer_str = ""
                    if is_prompt: buffer_str = "" 

        except Exception as e:
            self.logs.append(f"Erro no stream: {e}")
        finally:
            self.running = False
            self.logs.append(">>> Processo finalizado <<<")
            
            # --- Lógica de Playlist Condicional ---
            if self.is_playlist:
                time.sleep(2)
                try:
                    msg = generate_m3u_playlist(self.current_format)
                    if msg:
                        self.logs.append(f"✅ {msg}")
                    else:
                        self.logs.append("ℹ️ Playlist: Arquivo não gerado (sem arquivos encontrados).")
                except Exception as e:
                    self.logs.append(f"❌ Erro Playlist: {e}")
            else:
                # Se não for playlist, não faz nada (silencioso) ou avisa no log debug
                pass

# Instâncias Globais
wrapper = WrapperManager()
downloader = DownloaderManager()