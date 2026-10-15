"""
Security & Credential Protection Module for RGU SMTP Dispatcher
Provides:
- Symmetric at-rest encryption (Fernet / AES-128-CBC + HMAC) for sensitive tokens
- Safe masking for API responses
- Secure environment loading
"""

import os
import base64
import hashlib
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Load local environment variables from .env if present
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / '.env'
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

SECRET_KEY_FILE = BASE_DIR / '.secret_key'

def _get_or_create_key() -> bytes:
    """
    Retrieves or generates a stable 32-byte Fernet key.
    Priority:
    1. APP_SECRET_KEY / ENCRYPTION_KEY environment variable
    2. Local .secret_key file (automatically generated, strictly gitignored)
    """
    env_key = os.getenv('APP_SECRET_KEY') or os.getenv('ENCRYPTION_KEY') or os.getenv('SECRET_KEY')
    if env_key:
        # If env_key is not 32 url-safe base64 bytes, derive via SHA256
        try:
            # Check if valid Fernet key
            Fernet(env_key.encode('utf-8'))
            return env_key.encode('utf-8')
        except Exception:
            derived = base64.urlsafe_b64encode(hashlib.sha256(env_key.encode('utf-8')).digest())
            return derived

    if SECRET_KEY_FILE.exists():
        try:
            with open(SECRET_KEY_FILE, 'rb') as f:
                key = f.read().strip()
                if key:
                    Fernet(key)
                    return key
        except Exception:
            pass

    # Generate a fresh key and save securely
    new_key = Fernet.generate_key()
    try:
        with open(SECRET_KEY_FILE, 'wb') as f:
            f.write(new_key)
        # On POSIX set 0600 permissions
        try:
            os.chmod(SECRET_KEY_FILE, 0o600)
        except Exception:
            pass
    except Exception as e:
        print(f"Warning: Could not save .secret_key to disk: {e}")

    return new_key

_cipher = None

def get_cipher() -> Fernet:
    global _cipher
    if _cipher is None:
        key = _get_or_create_key()
        _cipher = Fernet(key)
    return _cipher

def encrypt_credential(plain_text: str) -> str:
    """
    Encrypts a plain text credential (e.g. Gmail App Password, Gemini API Key).
    Returns 'enc:<token>' string. If already encrypted or empty, returns as-is.
    """
    if not plain_text or not isinstance(plain_text, str):
        return ""
    plain_text = plain_text.strip()
    if not plain_text:
        return ""
    if plain_text.startswith("enc:"):
        return plain_text

    try:
        cipher = get_cipher()
        encrypted_bytes = cipher.encrypt(plain_text.encode('utf-8'))
        return f"enc:{encrypted_bytes.decode('utf-8')}"
    except Exception as e:
        print(f"Credential encryption error: {e}")
        return plain_text

def decrypt_credential(cipher_text: str) -> str:
    """
    Decrypts an 'enc:<token>' credential back into plain text for internal runtime usage.
    If plain text, returns as-is (backward compatible).
    """
    if not cipher_text or not isinstance(cipher_text, str):
        return ""
    cipher_text = cipher_text.strip()
    if not cipher_text:
        return ""
    if not cipher_text.startswith("enc:"):
        return cipher_text

    raw_token = cipher_text[4:]
    try:
        cipher = get_cipher()
        decrypted_bytes = cipher.decrypt(raw_token.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        print(f"Credential decryption error (key mismatch?): {e}")
        return ""

def mask_credential(value: str, prefix_len=0, suffix_len=0) -> str:
    """
    Creates a safe masked representation of a secret for UI presentation.
    Never exposes raw secrets over network APIs.
    """
    if not value or not isinstance(value, str):
        return ""
    # If encrypted, decrypt temporarily to determine shape
    actual = decrypt_credential(value)
    if not actual:
        return ""

    n = len(actual)
    if prefix_len > 0 and suffix_len > 0 and n > (prefix_len + suffix_len + 2):
        return actual[:prefix_len] + "••••••••" + actual[-suffix_len:]
    return "••••••••••••••••"
