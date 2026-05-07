from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt  # type: ignore[import-not-found,import-untyped]

from mvm_bot.config import jwt_secret
from mvm_bot.constants import CONNECT_REDIRECT_ORIGIN


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


def connect_redirect_url(tg_id: int) -> str:
    token = sign_tg_auth_jwt(tg_id)
    deep_link = f"mvmvpn://auth/{token}"
    return f"{CONNECT_REDIRECT_ORIGIN}/?{urlencode({'redirect': deep_link})}"


def connect_redirect_url_vk(vk_id: int) -> str:
    token = sign_vk_auth_jwt(vk_id)
    deep_link = f"mvmvpn://auth/{token}"
    return f"{CONNECT_REDIRECT_ORIGIN}/?{urlencode({'redirect': deep_link})}"
