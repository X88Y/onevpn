from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

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
    """Returns the redirect URL for the subscription (Telegram)."""
    sub_id = await get_or_provision_sub_id_tg(tg_id)
    if not sub_id:
        return f"https://getlifetimesubscription-caas3uwkra-ew.a.run.app?tgId={tg_id}"
    sub_url = f"https://getsubscription-caas3uwkra-ew.a.run.app/?id={sub_id}"
    happ_deeplink = f"happ://add/{sub_url}"
    return f"{CONNECT_REDIRECT_ORIGIN}/sub?redir={quote(happ_deeplink, safe='')}"


def connect_redirect_url_legacy(tg_id: int) -> str:
    """Returns the legacy redirect URL for the MVM app (Telegram)."""
    token = sign_tg_auth_jwt(tg_id)
    deep_link = f"mvmvpn://auth/{token}"
    return f"{CONNECT_REDIRECT_ORIGIN}/?{urlencode({'redirect': deep_link})}"


async def connect_redirect_url_vk(vk_id: int) -> str:
    """Returns the redirect URL for the subscription (VK)."""
    sub_id = await get_or_provision_sub_id_vk(vk_id)
    if not sub_id:
        return f"https://getlifetimesubscription-caas3uwkra-ew.a.run.app?vkId={vk_id}"
    sub_url = f"https://getsubscription-caas3uwkra-ew.a.run.app/?id={sub_id}"
    happ_deeplink = f"happ://add/{sub_url}"
    return f"{CONNECT_REDIRECT_ORIGIN}/sub?redir={quote(happ_deeplink, safe='')}"


def connect_redirect_url_vk_legacy(vk_id: int) -> str:
    """Returns the legacy redirect URL for the MVM app (VK)."""
    token = sign_vk_auth_jwt(vk_id)
    deep_link = f"mvmvpn://auth/{token}"
    return f"{CONNECT_REDIRECT_ORIGIN}/?{urlencode({'redirect': deep_link})}"

