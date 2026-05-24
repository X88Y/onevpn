import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from firebase_admin import firestore  # type: ignore[import-not-found,import-untyped]

from mvm_bot.config import remnawave_internal_squad_uuid
from mvm_bot.datetime_utils import as_utc_datetime
from mvm_bot.firebase_client import init_firebase
from mvm_bot.remnawave_client import (
    create_user as rw_create_user,
    update_user as rw_update_user,
    get_user_by_username as rw_get_user_by_username,
)
from mvm_bot.user_service.helpers import _remnawave_username, telegram_uid, vk_uid

logger = logging.getLogger(__name__)


async def _ensure_remnawave_user(
    user_uid: str,
    user_data: dict,
    *,
    telegram_id: Optional[int] = None,
) -> dict:
    """Ensure a Remnawave user exists and sync its metadata to Firestore.

    Returns the (possibly updated) user_data dict.
    """
    if user_data.get("remnawaveUuid") and user_data.get("remnawaveSubscriptionUrl"):
        # Sync current subscription state to Remnawave
        rw_uuid = user_data["remnawaveUuid"]
        end = as_utc_datetime(user_data.get("subscriptionEndsAt"))
        now = datetime.now(timezone.utc)
        if end is None:
            end = now
        status = "ACTIVE" if end > now else "DISABLED"
        try:
            await rw_update_user(uuid=str(rw_uuid), expire_at=end, status=status)
        except Exception:
            logger.exception("Failed to sync Remnawave user %s", rw_uuid)
        return user_data

    username = _remnawave_username(user_uid)
    rw_user = await rw_get_user_by_username(username)

    if rw_user is None:
        now = datetime.now(timezone.utc)
        squad = remnawave_internal_squad_uuid()
        squads = [squad] if squad else None
        try:
            rw_user = await rw_create_user(
                username=username,
                expire_at=now,
                telegram_id=telegram_id,
                status="ACTIVE",
                active_internal_squads=squads,
                description=f"MVM user {user_uid}",
            )
        except Exception:
            logger.exception("Failed to create Remnawave user for %s", user_uid)
            return user_data

    rw_uuid = str(rw_user.get("uuid") or "")
    rw_short = str(rw_user.get("shortUuid") or "")
    rw_sub_url = str(rw_user.get("subscriptionUrl") or "")
    if rw_uuid and rw_sub_url:
        db = init_firebase()
        users_ref = db.collection("users").document(user_uid)
        await asyncio.to_thread(
            lambda: users_ref.update(
                {
                    "remnawaveUuid": rw_uuid,
                    "remnawaveShortUuid": rw_short,
                    "remnawaveSubscriptionUrl": rw_sub_url,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                }
            )
        )
        user_data = {
            **user_data,
            "remnawaveUuid": rw_uuid,
            "remnawaveShortUuid": rw_short,
            "remnawaveSubscriptionUrl": rw_sub_url,
        }
    return user_data


async def _update_remnawave_subscription(
    user_uid: str,
    subscription_ends_at: Optional[datetime] = None,
) -> None:
    """Push the current subscription expiry (and status) to Remnawave."""
    db = init_firebase()
    users_ref = db.collection("users").document(user_uid)
    snap = await asyncio.to_thread(users_ref.get)
    if not snap.exists:
        return
    data = snap.to_dict() or {}
    rw_uuid = data.get("remnawaveUuid")

    if not rw_uuid:
        username = _remnawave_username(user_uid)
        rw_user = await rw_get_user_by_username(username)
        if not rw_user:
            # Fallback to old format for backward compatibility
            old_username = f"mvm-{user_uid}"
            if old_username != username:
                rw_user = await rw_get_user_by_username(old_username)
        if rw_user:
            rw_uuid = str(rw_user.get("uuid") or "")
            rw_short = str(rw_user.get("shortUuid") or "")
            rw_sub_url = str(rw_user.get("subscriptionUrl") or "")
            if rw_uuid and rw_sub_url:
                await asyncio.to_thread(
                    lambda: users_ref.update(
                        {
                            "remnawaveUuid": rw_uuid,
                            "remnawaveShortUuid": rw_short,
                            "remnawaveSubscriptionUrl": rw_sub_url,
                            "updatedAt": firestore.SERVER_TIMESTAMP,
                        }
                    )
                )
        else:
            logger.warning(
                "Cannot update Remnawave subscription: user %s not found in Remnawave",
                user_uid,
            )
            return

    now = datetime.now(timezone.utc)
    if subscription_ends_at is None:
        subscription_ends_at = now

    status = "ACTIVE" if subscription_ends_at > now else "DISABLED"
    try:
        await rw_update_user(
            uuid=str(rw_uuid),
            expire_at=subscription_ends_at,
            status=status,
        )
    except Exception:
        logger.exception("Failed to update Remnawave user %s", rw_uuid)


async def get_remnawave_sub_url(user_uid: str) -> Optional[str]:
    db = init_firebase()
    snap = await asyncio.to_thread(
        lambda: db.collection("users").document(user_uid).get()
    )
    if snap.exists:
        data = snap.to_dict() or {}
        if sub_url := data.get("remnawaveSubscriptionUrl"):
            return str(sub_url)
    return None


async def get_remnawave_sub_url_tg(tg_id: int) -> Optional[str]:
    db = init_firebase()
    auth_uid = telegram_uid(tg_id)
    users_ref = db.collection("users")
    user_docs = await asyncio.to_thread(
        lambda: users_ref.where("externalTg", "in", [auth_uid, str(tg_id)])
        .limit(1)
        .get()
    )
    if not user_docs:
        return None
    user_doc = user_docs[0]
    data = user_doc.to_dict() or {}
    if sub_url := data.get("remnawaveSubscriptionUrl"):
        return str(sub_url)

    # Fallback: ensure user exists in Remnawave
    from aiogram.types import User  # type: ignore[import-not-found]
    try:
        from mvm_bot.user_service.core import save_telegram_user
        _, data = await save_telegram_user(User(id=tg_id, is_bot=False, first_name=""))
        return data.get("remnawaveSubscriptionUrl")
    except Exception:
        logger.exception("Failed to ensure Remnawave user for tg %s", tg_id)
        return None


async def get_remnawave_sub_url_vk(vk_id: int) -> Optional[str]:
    db = init_firebase()
    auth_uid = vk_uid(vk_id)
    users_ref = db.collection("users")
    user_docs = await asyncio.to_thread(
        lambda: users_ref.where("externalVk", "in", [auth_uid, str(vk_id)])
        .limit(1)
        .get()
    )
    if not user_docs:
        return None
    user_doc = user_docs[0]
    data = user_doc.to_dict() or {}
    if sub_url := data.get("remnawaveSubscriptionUrl"):
        return str(sub_url)
    return None
