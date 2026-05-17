from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

import jwt  # type: ignore[import-not-found,import-untyped]

from mvm_bot.config import jwt_secret
from mvm_bot.constants import CONNECT_REDIRECT_ORIGIN
from mvm_bot.user_service import get_remnawave_sub_url_tg, get_remnawave_sub_url_vk


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


async def connect_redirect_url(tg_id: int, data: Optional[dict] = None) -> str:
    """Returns the redirect URL for the subscription (Telegram)."""
    sub_url = None
    if data and data.get("remnawaveSubscriptionUrl"):
        sub_url = data["remnawaveSubscriptionUrl"]
    else:
        sub_url = await get_remnawave_sub_url_tg(tg_id)
    if not sub_url:
        return f"https://getlifetimesubscription-caas3uwkra-ew.a.run.app?tgId={tg_id}"
    happ_deeplink = f"happ://add/{sub_url}"
    return f"{CONNECT_REDIRECT_ORIGIN}/sub?redir={quote(happ_deeplink, safe='')}"


async def connect_redirect_url_vk(vk_id: int, data: Optional[dict] = None) -> str:
    """Returns the redirect URL for the subscription (VK)."""
    sub_url = None
    if data and data.get("remnawaveSubscriptionUrl"):
        sub_url = data["remnawaveSubscriptionUrl"]
    else:
        sub_url = await get_remnawave_sub_url_vk(vk_id)
    if not sub_url:
        return f"https://getlifetimesubscription-caas3uwkra-ew.a.run.app?vkId={vk_id}"
    happ_deeplink = f"happ://add/{sub_url}"
    return f"{CONNECT_REDIRECT_ORIGIN}/sub?redir={quote(happ_deeplink, safe='')}"
