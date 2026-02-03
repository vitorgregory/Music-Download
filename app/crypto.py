from cryptography.fernet import Fernet
import os
from pathlib import Path

KEY_ENV = "CREDENTIALS_KEY"
KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "secret.key")


def _ensure_key_file():
    Path(os.path.dirname(KEY_FILE)).mkdir(parents=True, exist_ok=True)
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)
    try:
        os.chmod(KEY_FILE, 0o600)
    except Exception:
        pass
    return key


def get_key() -> bytes:
    env_key = os.environ.get(KEY_ENV)
    if env_key:
        # Allow passing raw base64 key via env
        return env_key.encode()
    return _ensure_key_file()


def encrypt_str(s: str) -> str:
    f = Fernet(get_key())
    return f.encrypt(s.encode()).decode()


def decrypt_str(token: str) -> str:
    f = Fernet(get_key())
    return f.decrypt(token.encode()).decode()
