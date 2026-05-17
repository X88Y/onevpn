"""Remnawave client for the bot."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from mvm_bot.config import remnawave_api_token, remnawave_base_url

from remnawave import RemnawaveSDK


logger = logging.getLogger(__name__)


class RemnawaveError(RuntimeError):
    pass


_sdk_instance: Optional[Any] = None

_base = remnawave_base_url()
_token = remnawave_api_token()
print(f"Remnawave base URL: {_base}")
print(f"Remnawave API token: {_token[:4]}...{_token[-4:]}")
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
    from remnawave.enums import TrafficLimitStrategy, UserStatus
    from remnawave.models import CreateUserRequestDto

    squads = None
    if active_internal_squads:
        from uuid import UUID

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
) -> Dict[str, Any]:
    if _sdk_instance is None:
        raise RemnawaveError(
            "Remnawave not configured: set REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN"
        )
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
