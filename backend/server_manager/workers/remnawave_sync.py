"""Periodic sync of subscription expiry status from Firestore to Remnawave."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from firebase_admin import firestore

from server_manager.config import settings
from server_manager.firestore_client import init_firestore
from server_manager.remnawave.client import update_user

logger = logging.getLogger(__name__)


def _expiry_from_user_data(user_data: Dict[str, Any]) -> tuple[Optional[datetime], bool]:
    """Returns (expire_at, is_active) from a user document dict."""
    end = user_data.get("subscriptionEndsAt")
    if end is None:
        return None, False
    if hasattr(end, "timestamp"):
        end_dt = end
    else:
        try:
            end_dt = datetime.fromisoformat(str(end))
        except Exception:  # noqa: BLE001
            return None, False
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return end_dt, end_dt > now


async def _sync_once(db: firestore.Client) -> None:
    # Fetch users that have been linked to Remnawave
    user_snaps = await asyncio.to_thread(
        lambda: list(
            db.collection("users")
            .where("remnawaveUuid", ">", "")
            .stream()
        )
    )
    if not user_snaps:
        return

    updates: List[asyncio.Task] = []
    for snap in user_snaps:
        data = snap.to_dict() or {}
        rw_uuid = data.get("remnawaveUuid")
        if not rw_uuid:
            continue
        expire_at, is_active = _expiry_from_user_data(data)
        if expire_at is None:
            expire_at = datetime.now(timezone.utc)
        status = "ACTIVE" if is_active else "DISABLED"

        async def _do(uuid: str = str(rw_uuid), exp: datetime = expire_at, st: str = status) -> None:
            try:
                await update_user(uuid=uuid, expire_at=exp, status=st)
            except Exception:
                logger.exception("remnawave sync failed uuid=%s", uuid)

        updates.append(asyncio.create_task(_do()))

    if updates:
        await asyncio.gather(*updates, return_exceptions=True)


async def run_remnawave_sync_loop() -> None:
    if not settings.remnawave_base_url or not settings.remnawave_api_token:
        logger.info("Remnawave sync disabled: set REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN")
        return

    db = init_firestore()
    interval = max(60, settings.remnawave_sync_interval_s)
    logger.info("remnawave sync worker started interval=%ss", interval)
    while True:
        try:
            await _sync_once(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("remnawave sync iteration failed")
        await asyncio.sleep(interval)
