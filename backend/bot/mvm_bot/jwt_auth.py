from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt  # type: ignore[import-not-found,import-untyped]

from mvm_bot.config import jwt_secret, manager_base_url
from mvm_bot.constants import CONNECT_REDIRECT_ORIGIN
from mvm_bot.user_service import get_or_provision_sub_id_tg, get_or_provision_sub_id_vk


def sign_tg_auth_jwt(tg_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "provider": "tg",
        "user": str(tg_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=24 * 30)).timestamp()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm="HS256")


def sign_vk_auth_jwt(vk_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "provider": "vk",
        "user": str(vk_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=24 * 30)).timestamp()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm="HS256")


async def connect_redirect_url(tg_id: int) -> str:
    """Returns the Cloud Function URL for the lifetime subscription (Telegram)."""
    return f"https://getlifetimesubscription-caas3uwkra-uc.a.run.app?tgId={tg_id}"


async def connect_redirect_url_vk(vk_id: int) -> str:
    """Returns the Cloud Function URL for the lifetime subscription (VK)."""
    return f"https://getlifetimesubscription-caas3uwkra-uc.a.run.app?vkId={vk_id}"
