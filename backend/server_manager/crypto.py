import threading
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from server_manager.config import settings

_lock = threading.Lock()
_fernet_instance: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """Build Fernet lazily so `generate_key()` works before a valid key is in .env."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance
    with _lock:
        if _fernet_instance is not None:
            return _fernet_instance
        raw = settings.fernet_key.strip()
        try:
            _fernet_instance = Fernet(raw.encode("ascii"))
        except ValueError as exc:
            raise RuntimeError(
                "SERVER_MANAGER_FERNET_KEY is invalid. Generate a key with:\n"
                "  python -m server_manager.gen_fernet_key\n"
                "or: python3 -c \"from cryptography.fernet import Fernet; "
                'print(Fernet.generate_key().decode())"'
            ) from exc
        return _fernet_instance


def encrypt_str(plaintext: str) -> str:
    if plaintext is None:
        raise ValueError("plaintext is required")
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_str(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Failed to decrypt secret value") from exc


def generate_key() -> str:
    """Return a new url-safe base64 Fernet key (does not read SERVER_MANAGER_FERNET_KEY)."""
    return Fernet.generate_key().decode("ascii")
