import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram.types import User  # type: ignore[import-not-found]
from firebase_admin import firestore  # type: ignore[import-not-found,import-untyped]

from mvm_bot.config import remnawave_internal_squad_uuid
from mvm_bot.constants import PREMIUM_EXTERNAL_SQUAD_UUID, PREMIUM_INTERNAL_SQUAD_UUID
from mvm_bot.datetime_utils import as_utc_datetime
from mvm_bot.firebase_client import init_firebase
from mvm_bot.remnawave_client import (
    _sdk_instance,
    create_user as rw_create_user,
    update_user as rw_update_user,
    get_user_by_username as rw_get_user_by_username,
)
from mvm_bot.user_service.helpers import (
    _remnawave_username,
    telegram_uid,
    vk_uid,
)
logger = logging.getLogger(__name__)


async def _apply_remnawave_status(
    rw_uuid: str,
    current_status: str,
    target_status: str,
    expire_at: Optional[datetime],
    description: Optional[str] = None,
    tier: Optional[str] = None,
) -> None:
    """Apply status + metadata to a Remnawave user.

    Remnawave only accepts ACTIVE/DISABLED in PATCH; EXPIRED/LIMITED are managed
    internally and are rejected when sent. We therefore:
    - Update metadata (expire_at only for ACTIVE, description) via PATCH.
    - Change status only via the dedicated action endpoints (enable/disable).
    - Apply tier-specific squads (premium gets squad, standart removes it).
    """
    # Build keyword args for the metadata PATCH (no status field)
    kwargs: dict = {}
    if target_status == "ACTIVE" and expire_at is not None:
        kwargs["expire_at"] = expire_at
    if description is not None:
        kwargs["description"] = description

    # Apply tier-based squads
    if tier == "premium":
        kwargs["active_internal_squads"] = [PREMIUM_INTERNAL_SQUAD_UUID]
        kwargs["external_squad_uuid"] = PREMIUM_EXTERNAL_SQUAD_UUID
    elif tier == "standart":
        # Remove premium squads — assign default squad or empty
        default_squad = remnawave_internal_squad_uuid()
        kwargs["active_internal_squads"] = [default_squad] if default_squad else []

    if kwargs:
        await rw_update_user(uuid=rw_uuid, **kwargs)

    # Apply status change via dedicated action endpoints
    current = current_status.upper()
    target = target_status.upper()
    if target == "ACTIVE" and current != "ACTIVE":
        if _sdk_instance is not None:
            try:
                await _sdk_instance.users.enable_user(uuid=rw_uuid)
            except Exception as exc:
                exc_str = str(exc).lower()
                if "already enabled" in exc_str or "a030" in exc_str:
                    logger.debug("enable_user ignored (already active) uuid=%s", rw_uuid)
                else:
                    raise
    elif target == "DISABLED" and current == "ACTIVE":
        if _sdk_instance is not None:
            try:
                await _sdk_instance.users.disable_user(uuid=rw_uuid)
            except Exception as exc:
                exc_str = str(exc).lower()
                if "already disabled" in exc_str:
                    logger.debug("disable_user ignored (already disabled) uuid=%s", rw_uuid)
                else:
                    raise


async def build_user_description(user_uid: str, user_data: dict) -> str:
    parts = [f"MVM user {user_uid}"]

    external_tg = user_data.get("externalTg")
    external_vk = user_data.get("externalVk")

    db = init_firebase()

    if external_tg:
        tg_id = None
        tg_username = None
        if isinstance(external_tg, str):
            if external_tg.startswith("tg:"):
                tg_id = external_tg[3:]
            else:
                tg_id = external_tg
        elif isinstance(external_tg, (int, float)):
            tg_id = str(int(external_tg))

        if tg_id:
            try:
                tg_doc_ref = db.collection("telegram_users").document(f"tg:{tg_id}")
                tg_snap = await asyncio.to_thread(tg_doc_ref.get)
                if tg_snap.exists:
                    tg_info = tg_snap.to_dict() or {}
                    tg_username = tg_info.get("username")
                    if tg_info.get("tgId"):
                        tg_id = str(tg_info.get("tgId"))
            except Exception:
                logger.exception("Failed to fetch telegram user info for %s", external_tg)

        if tg_username:
            parts.append(f"TG: https://t.me/{tg_username}")
        elif tg_id:
            parts.append(f"TG: tg://user?id={tg_id}")

    if external_vk:
        vk_id = None
        vk_screen_name = None
        if isinstance(external_vk, str):
            if external_vk.startswith("vk:"):
                vk_id = external_vk[3:]
            else:
                vk_id = external_vk
        elif isinstance(external_vk, (int, float)):
            vk_id = str(int(external_vk))

        if vk_id:
            try:
                vk_doc_ref = db.collection("vk_users").document(f"vk:{vk_id}")
                vk_snap = await asyncio.to_thread(vk_doc_ref.get)
                if vk_snap.exists:
                    vk_info = vk_snap.to_dict() or {}
                    vk_screen_name = vk_info.get("screenName")
                    if vk_info.get("vkId"):
                        vk_id = str(vk_info.get("vkId"))
            except Exception:
                logger.exception("Failed to fetch vk user info for %s", external_vk)

        if vk_screen_name:
            parts.append(f"VK: https://vk.com/{vk_screen_name}")
        elif vk_id:
            parts.append(f"VK: https://vk.com/id{vk_id}")

    return " | ".join(parts)


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
        current_tier = user_data.get("subscriptionTier")
        try:
            # Fetch current status to decide which action endpoint to call
            current_status = "UNKNOWN"
            if _sdk_instance is not None:
                try:
                    rw_user_resp = await _sdk_instance.users.get_user_by_uuid(uuid=str(rw_uuid))
                    current_status = str(rw_user_resp.status).upper()
                except Exception:
                    pass  # proceed with best-effort
            desc = await build_user_description(user_uid, user_data)
            await _apply_remnawave_status(
                rw_uuid=str(rw_uuid),
                current_status=current_status,
                target_status=status,
                expire_at=end,
                description=desc,
                tier=current_tier if status == "ACTIVE" else None,
            )
        except Exception:
            logger.exception("Failed to sync Remnawave user %s", rw_uuid)
        return user_data

    username = _remnawave_username(user_uid)
    rw_user = await rw_get_user_by_username(username)

    current_tier = user_data.get("subscriptionTier")
    end = as_utc_datetime(user_data.get("subscriptionEndsAt"))
    now = datetime.now(timezone.utc)
    expire_at = end if end is not None else now
    is_active = expire_at > now

    if rw_user is None:
        # Determine squads based on the user's current tier so a user who
        # already paid premium is placed in the correct squad immediately.
        if current_tier == "premium" and is_active:
            initial_squads = [PREMIUM_INTERNAL_SQUAD_UUID]
        else:
            default_squad = remnawave_internal_squad_uuid()
            initial_squads = [default_squad] if default_squad else None

        try:
            desc = await build_user_description(user_uid, user_data)
            rw_user = await rw_create_user(
                username=username,
                expire_at=expire_at,
                telegram_id=telegram_id,
                status="ACTIVE" if is_active else "DISABLED",
                active_internal_squads=initial_squads,
                description=desc,
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

        # Sync subscription state and squad membership for users found by
        # username (UUID was not previously stored in Firestore). This covers
        # the case where a user purchased premium before their first bot login.
        try:
            rw_current_status = str(rw_user.get("status") or "UNKNOWN").upper()
            desc = await build_user_description(user_uid, user_data)
            await _apply_remnawave_status(
                rw_uuid=rw_uuid,
                current_status=rw_current_status,
                target_status="ACTIVE" if is_active else "DISABLED",
                expire_at=expire_at,
                description=desc,
                tier=current_tier if is_active else None,
            )
        except Exception:
            logger.exception(
                "Failed to sync Remnawave status/squads for new uuid=%s uid=%s",
                rw_uuid,
                user_uid,
            )
    return user_data


async def _update_remnawave_subscription(
    user_uid: str,
    subscription_ends_at: Optional[datetime] = None,
    tier: Optional[str] = None,
) -> None:
    """Push the current subscription expiry (and status) to Remnawave.

    When *tier* is provided, also applies the appropriate squad config:
    - "premium" → assign premium external/internal squads
    - "standart" → remove premium squads, revert to default
    """
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

    # Use tier from param, fall back to Firestore document
    effective_tier = tier or data.get("subscriptionTier")

    now = datetime.now(timezone.utc)
    if subscription_ends_at is None:
        subscription_ends_at = now

    status = "ACTIVE" if subscription_ends_at > now else "DISABLED"
    try:
        # Fetch current status to decide which action endpoint to call
        current_status = "UNKNOWN"
        if _sdk_instance is not None:
            try:
                rw_user_resp = await _sdk_instance.users.get_user_by_uuid(uuid=str(rw_uuid))
                current_status = str(rw_user_resp.status).upper()
            except Exception:
                pass  # proceed with best-effort
        desc = await build_user_description(user_uid, data)
        await _apply_remnawave_status(
            rw_uuid=str(rw_uuid),
            current_status=current_status,
            target_status=status,
            expire_at=subscription_ends_at,
            description=desc,
            tier=effective_tier if status == "ACTIVE" else None,
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
