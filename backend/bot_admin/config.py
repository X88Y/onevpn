import os
from pathlib import Path
from typing import Optional, Set

from bot_admin.constants import BOT_ADMIN_DIR


def env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def bot_token() -> str:
    token = env("TELEGRAM_BOT_TOKEN") or env("BOT_TOKEN")
    if token is None:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN or BOT_TOKEN in bot_admin/.env")
    return token


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
        BOT_ADMIN_DIR / credential_path,
        BOT_ADMIN_DIR.parent / credential_path,
        BOT_ADMIN_DIR.parent / "bot" / credential_path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[0])


def manager_base_url() -> str:
    raw = env("MANAGER_BASE_URL")
    if raw is None:
        raise RuntimeError("Set MANAGER_BASE_URL in bot_admin/.env")
    return raw.rstrip("/")


def manager_api_key() -> str:
    raw = env("MANAGER_API_KEY")
    if raw is None:
        raise RuntimeError("Set MANAGER_API_KEY in bot_admin/.env")
    return raw


def platega_merchant_id() -> str:
    value = env("PLATEGA_MERCHANT_ID")
    if value is None:
        raise RuntimeError("Set PLATEGA_MERCHANT_ID in bot_admin/.env")
    return value


def platega_secret() -> str:
    value = env("PLATEGA_SECRET")
    if value is None:
        raise RuntimeError("Set PLATEGA_SECRET in bot_admin/.env")
    return value


def platega_return_url() -> str:
    return env("PLATEGA_RETURN_URL") or "https://t.me"


def platega_failed_url() -> str:
    return env("PLATEGA_FAILED_URL") or "https://t.me"


def admin_telegram_ids() -> Set[int]:
    raw = env("ADMIN_TELEGRAM_IDS")
    if raw is None:
        raise RuntimeError(
            "Set ADMIN_TELEGRAM_IDS in bot_admin/.env (comma-separated Telegram user IDs)"
        )
    ids: Set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        ids.add(int(part))
    if not ids:
        raise RuntimeError("ADMIN_TELEGRAM_IDS must contain at least one numeric user ID")
    return ids
