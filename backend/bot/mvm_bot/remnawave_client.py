"""Remnawave client for the bot."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx

from mvm_bot.config import remnawave_api_token, remnawave_base_url

from remnawave import RemnawaveSDK
from remnawave.enums import TrafficLimitStrategy, UserStatus
from remnawave.models import CreateUserRequestDto, UpdateUserRequestDto


logger = logging.getLogger(__name__)


class RemnawaveError(RuntimeError):
    pass


_sdk_instance: Optional[Any] = None

_base = remnawave_base_url()
_token = remnawave_api_token()
print(f"Remnawave base URL: {_base}")
if _token:
    print(f"Remnawave API token: {_token[:4]}...{_token[-4:]}")
else:
    print("Remnawave API token: None")
if _base and _token:
    _sdk_instance = RemnawaveSDK(base_url=_base, token=_token)


def _user_to_dict(resp: Any) -> Dict[str, Any]:
    return resp.model_dump(by_alias=True, mode="json")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    if _sdk_instance is None:
        raise RemnawaveError("Remnawave not configured")
    try:
        resp = await _sdk_instance.users.get_user_by_username(username)
        return _user_to_dict(resp)
    except Exception as exc:
        if "404" in str(exc) or "not found" in str(exc).lower():
            return None
        logger.exception("Remnawave get_user_by_username failed")
        raise


async def create_user(
    username: str,
    expire_at: datetime,
    *,
    telegram_id: Optional[int] = None,
    status: str = "ACTIVE",
    traffic_limit_strategy: str = "NO_RESET",
    active_internal_squads: Optional[List[str]] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    if _sdk_instance is None:
        raise RemnawaveError(
            "Remnawave not configured: set REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN"
        )
    squads = None
    if active_internal_squads:
        squads = [UUID(s) for s in active_internal_squads]

    body = CreateUserRequestDto(
        username=username,
        expire_at=expire_at,
        status=UserStatus(status),
        traffic_limit_strategy=TrafficLimitStrategy(traffic_limit_strategy),
        telegram_id=telegram_id,
        active_internal_squads=squads,
        description=description,
    )
    resp = await _sdk_instance.users.create_user(body)
    return _user_to_dict(resp)


async def update_user(
    uuid: str,
    *,
    expire_at: Optional[datetime] = None,
    status: Optional[str] = None,
    traffic_limit_strategy: Optional[str] = None,
    traffic_limit_bytes: Optional[int] = None,
    description: Optional[str] = None,
    active_internal_squads: Optional[List[str]] = None,
    external_squad_uuid: Optional[str] = None,
) -> Dict[str, Any]:
    if _sdk_instance is None:
        raise RemnawaveError(
            "Remnawave not configured: set REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN"
        )
    body = UpdateUserRequestDto(uuid=UUID(uuid))
    if expire_at is not None:
        body.expire_at = expire_at
    if status is not None:
        body.status = UserStatus(status)
    if traffic_limit_strategy is not None:
        body.traffic_limit_strategy = TrafficLimitStrategy(traffic_limit_strategy)
    if traffic_limit_bytes is not None:
        body.traffic_limit_bytes = traffic_limit_bytes
    if description is not None:
        body.description = description
    if active_internal_squads is not None:
        body.active_internal_squads = [UUID(s) for s in active_internal_squads]
    if external_squad_uuid is not None:
        body.external_squad_uuid = UUID(external_squad_uuid)

    resp = await _sdk_instance.users.update_user(body)
    return _user_to_dict(resp)


async def get_user_hwid_devices(user_uuid: str) -> List[Dict[str, Any]]:
    if not _base or not _token:
        raise RemnawaveError("Remnawave not configured")
    
    url = f"{_base}/api/hwid/devices/{user_uuid}"
    headers = {
        "Authorization": f"Bearer {_token}",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", {}).get("devices", [])
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return []
        logger.exception("Remnawave get_user_hwid_devices failed")
        raise RemnawaveError(f"HTTP error: {exc}")
    except Exception as exc:
        logger.exception("Remnawave get_user_hwid_devices failed")
        raise RemnawaveError(f"Request failed: {exc}")


async def delete_user_hwid_device(user_uuid: str, hwid: str) -> None:
    if not _base or not _token:
        raise RemnawaveError("Remnawave not configured")
    
    url = f"{_base}/api/hwid/devices/delete"
    headers = {
        "Authorization": f"Bearer {_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "userUuid": str(user_uuid),
        "hwid": hwid,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
    except Exception as exc:
        logger.exception("Remnawave delete_user_hwid_device failed")
        raise RemnawaveError(f"Request failed: {exc}")

