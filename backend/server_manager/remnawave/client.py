"""Remnawave client for server_manager."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

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


async def update_user(
    uuid: str,
    *,
    expire_at: Optional[datetime] = None,
    status: Optional[str] = None,
    traffic_limit_strategy: Optional[str] = None,
    traffic_limit_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    if _sdk_instance is None:
        raise RemnawaveError("Remnawave not configured")
    from remnawave.enums import TrafficLimitStrategy, UserStatus
    from remnawave.models import UpdateUserRequestDto
    from uuid import UUID

    body = UpdateUserRequestDto(uuid=UUID(uuid))
    if expire_at is not None:
        body.expire_at = expire_at
    if status is not None:
        body.status = UserStatus(status)
    if traffic_limit_strategy is not None:
        body.traffic_limit_strategy = TrafficLimitStrategy(traffic_limit_strategy)
    if traffic_limit_bytes is not None:
        body.traffic_limit_bytes = traffic_limit_bytes

    resp = await _sdk_instance.users.update_user(body)
    return _user_to_dict(resp)
