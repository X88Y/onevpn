import os
from pathlib import Path
from typing import Optional

from mvm_bot.constants import BOT_DIR, MENU_BANNER_PATH


def env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None

    value = value.strip()
    return value or None


def bot_token() -> str:
    token = env("TELEGRAM_BOT_TOKEN") or env("BOT_TOKEN")
    if token is None:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN or BOT_TOKEN in bot/.env")

    return token


def vk_bot_token() -> str:
    token = env("VK_BOT_TOKEN")
    if token is None:
        raise RuntimeError("Set VK_BOT_TOKEN in bot/.env")

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
        BOT_DIR / credential_path,
        BOT_DIR.parent / credential_path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return str(candidates[0])


def jwt_secret() -> str:
    secret = env("MVMVPN_JWT_SECRET")
    if secret is None:
        raise RuntimeError("Set MVMVPN_JWT_SECRET in bot/.env")

    return secret


def heleket_merchant_uuid() -> Optional[str]:
    return env("HELEKET_MERCHANT_UUID")


def heleket_payment_api_key() -> Optional[str]:
    return env("HELEKET_PAYMENT_API_KEY")


def heleket_callback_url() -> Optional[str]:
    """Webhook URL registered as ``url_callback`` on invoices (Firebase HTTPS function)."""
    return env("HELEKET_CALLBACK_URL")


def platega_merchant_id() -> Optional[str]:
    return env("PLATEGA_MERCHANT_ID")


def platega_secret() -> Optional[str]:
    return env("PLATEGA_SECRET")


def platega_return_url() -> str:
    return env("PLATEGA_RETURN_URL") or "https://t.me"


def platega_failed_url() -> str:
    return env("PLATEGA_FAILED_URL") or "https://t.me"


def freekassa_shop_id() -> Optional[int]:
    raw = env("FREEKASSA_SHOP_ID")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def freekassa_api_key() -> Optional[str]:
    return env("FREEKASSA_API_KEY")


def freekassa_ip() -> str:
    """IP address to pass to FreeKassa (must not be 127.0.0.1)."""
    return env("FREEKASSA_IP") or "0.0.0.0"


def freekassa_return_url() -> str:
    return env("FREEKASSA_RETURN_URL") or "https://t.me"


def menu_banner_path() -> Optional[Path]:
    configured = env("TELEGRAM_MENU_BANNER_PATH")
    path = Path(configured).expanduser() if configured else MENU_BANNER_PATH
    if path.exists():
        return path

    return None


def vk_menu_banner_path() -> Optional[Path]:
    configured = env("VK_MENU_BANNER_PATH") or env("TELEGRAM_MENU_BANNER_PATH")
    path = Path(configured).expanduser() if configured else MENU_BANNER_PATH
    if path.exists():
        return path

    return None


def manager_base_url() -> str:
    url = env("MANAGER_BASE_URL")
    if url is None:
        raise RuntimeError("Set MANAGER_BASE_URL in bot/.env")

    return url.rstrip("/")


def manager_api_key() -> str:
    key = env("MANAGER_API_KEY")
    if key is None:
        raise RuntimeError("Set MANAGER_API_KEY in bot/.env")

    return key
