"""Remnawave client for server_manager."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from server_manager.config import settings

logger = logging.getLogger(__name__)


class RemnawaveError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# SDK
# ---------------------------------------------------------------------------
_SDK_AVAILABLE = False
try:
    from remnawave import RemnawaveSDK

    _SDK_AVAILABLE = True
except Exception:  # noqa: BLE001
    pass

_sdk_instance: Optional[Any] = None
if _SDK_AVAILABLE:
    _base = settings.remnawave_base_url
    _token = settings.remnawave_api_token
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


_UNSET = object()


async def update_user(
    uuid: str,
    *,
    expire_at: Optional[datetime] = _UNSET,
    status: Optional[str] = _UNSET,
    traffic_limit_strategy: Optional[str] = _UNSET,
    traffic_limit_bytes: Optional[int] = _UNSET,
    description: Optional[str] = _UNSET,
    active_internal_squads: Optional[List[str]] = _UNSET,
    external_squad_uuid: Optional[str] = _UNSET,
) -> Dict[str, Any]:
    if _sdk_instance is None:
        raise RemnawaveError("Remnawave not configured")
    from remnawave.enums import TrafficLimitStrategy, UserStatus
    from remnawave.models import UpdateUserRequestDto
    from uuid import UUID

    body = UpdateUserRequestDto(uuid=UUID(uuid))
    if expire_at is not _UNSET:
        body.expire_at = expire_at
    if status is not _UNSET:
        body.status = UserStatus(status) if status is not None else None
    if traffic_limit_strategy is not _UNSET:
        body.traffic_limit_strategy = TrafficLimitStrategy(traffic_limit_strategy) if traffic_limit_strategy is not None else None
    if traffic_limit_bytes is not _UNSET:
        body.traffic_limit_bytes = traffic_limit_bytes
    if description is not _UNSET:
        body.description = description
    if active_internal_squads is not _UNSET:
        body.active_internal_squads = [UUID(s) for s in active_internal_squads] if active_internal_squads is not None else None
    if external_squad_uuid is not _UNSET:
        body.external_squad_uuid = UUID(external_squad_uuid) if external_squad_uuid is not None else None

    resp = await _sdk_instance.users.update_user(body)
    return _user_to_dict(resp)
