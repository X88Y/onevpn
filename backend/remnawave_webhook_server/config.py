import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

WEBHOOK_SERVER_DIR = Path(__file__).resolve().parent

# Load from current directory, or parent, or bot directory
env_paths = [
    WEBHOOK_SERVER_DIR / ".env",
    WEBHOOK_SERVER_DIR.parent / ".env",
    WEBHOOK_SERVER_DIR.parent / "bot" / ".env",
    WEBHOOK_SERVER_DIR.parent / "server_manager" / ".env",
]

for path in env_paths:
    if path.exists():
        load_dotenv(path)
        break

def env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None

def webhook_host() -> str:
    return env("REMNAWAVE_WEBHOOK_HOST") or "0.0.0.0"

def webhook_port() -> int:
    port_str = env("REMNAWAVE_WEBHOOK_PORT")
    if not port_str:
        return 8082
    try:
        return int(port_str)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid REMNAWAVE_WEBHOOK_PORT value: {port_str}. Must be an integer.") from exc

def webhook_secret() -> Optional[str]:
    return env("REMNAWAVE_WEBHOOK_SECRET") or env("WEBHOOK_SECRET_HEADER")

def bot_token() -> Optional[str]:
    return env("TELEGRAM_BOT_TOKEN") or env("BOT_TOKEN")

def service_account_path() -> Optional[str]:
    path = (
        env("FIREBASE_SERVICE_ACCOUNT_PATH")
        or env("FIREBASE_CREDENTIALS_PATH")
        or env("GOOGLE_APPLICATION_CREDENTIALS")
    )
    if path is None:
        return None
    
    credential_path = Path(path).expanduser()
    if credential_path.is_absolute():
        return str(credential_path)

    candidates = [
        Path.cwd() / credential_path,
        WEBHOOK_SERVER_DIR / credential_path,
        WEBHOOK_SERVER_DIR.parent / credential_path,
        WEBHOOK_SERVER_DIR.parent / "bot" / credential_path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return str(candidates[0])
