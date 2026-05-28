import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from aiogram.types import User  # type: ignore[import-not-found]
from firebase_admin import auth, firestore  # type: ignore[import-not-found,import-untyped]

from mvm_bot.constants import SUBSCRIPTION_PLANS, is_premium_plan
from mvm_bot.datetime_utils import as_utc_datetime
from mvm_bot.firebase_client import init_firebase
from mvm_bot.user_service.helpers import (
    VkProfile,
    _is_uuid,
    generate_referral_code,
    telegram_uid,
    vk_uid,
)
from mvm_bot.user_service.auth import ensure_auth_user, ensure_vk_auth_user
from mvm_bot.user_service.remnawave import _ensure_remnawave_user, _update_remnawave_subscription
from mvm_bot.user_service.referrals import _apply_referral_join_bonus
from mvm_bot.user_service.trial import _initial_trial_fields, _missing_trial_defaults

logger = logging.getLogger(__name__)


def _telegram_payload(
    uid: str,
    tg_user: User,
    auth_user: auth.UserRecord,
    exists: bool,
) -> dict:
    payload = {
        "uid": uid,
        "authUid": auth_user.uid,
        "tgId": str(tg_user.id),
        "username": tg_user.username,
        "firstName": tg_user.first_name,
        "lastName": tg_user.last_name,
        "languageCode": tg_user.language_code,
        "isBot": tg_user.is_bot,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if not exists:
        payload["createdAt"] = firestore.SERVER_TIMESTAMP

    return payload


def _vk_users_mirror_payload(
    uid: str,
    profile: VkProfile,
    auth_user: auth.UserRecord,
    exists: bool,
    group_id: Optional[int] = None,
) -> dict:
    payload = {
        "uid": uid,
        "authUid": auth_user.uid,
        "vkId": str(profile.id),
        "screenName": profile.screen_name,
        "firstName": profile.first_name,
        "lastName": profile.last_name,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if group_id is not None:
        payload["vkGroupId"] = str(group_id)
        payload["vkGroupIds"] = firestore.ArrayUnion([str(group_id)])
    if not exists:
        payload["createdAt"] = firestore.SERVER_TIMESTAMP

    return payload


def _users_payload(
    uid: str,
    tg_user: User,
    auth_user: auth.UserRecord,
    exists: bool,
    current_data: Optional[dict] = None,
    referral_code: Optional[str] = None,
) -> dict:
    current_data = current_data or {}
    payload = {
        "externalTg": telegram_uid(tg_user.id),
        "updatedAt": firestore.SERVER_TIMESTAMP,
        **_missing_trial_defaults(current_data),
    }
    if not current_data.get("referralCode"):
        payload["referralCode"] = generate_referral_code()
    if not exists:
        payload.update(
            {
                **_initial_trial_fields(),
                "externalAppleId": None,
                "externalVk": None,
                "referredByCode": referral_code,
                "createdAt": firestore.SERVER_TIMESTAMP,
            }
        )

    return payload


def _vk_users_document_payload(
    uid: str,
    profile: VkProfile,
    auth_user: auth.UserRecord,
    exists: bool,
    current_data: Optional[dict] = None,
    referral_code: Optional[str] = None,
    group_id: Optional[int] = None,
) -> dict:
    current_data = current_data or {}
    payload = {
        "externalVk": vk_uid(profile.id),
        "updatedAt": firestore.SERVER_TIMESTAMP,
        **_missing_trial_defaults(current_data),
    }
    if group_id is not None:
        payload["vkGroupId"] = str(group_id)
        payload["vkGroupIds"] = firestore.ArrayUnion([str(group_id)])
    if not current_data.get("referralCode"):
        payload["referralCode"] = generate_referral_code()
    if not exists:
        payload.update(
            {
                **_initial_trial_fields(),
                "externalAppleId": None,
                "externalTg": None,
                "referredByCode": referral_code,
                "createdAt": firestore.SERVER_TIMESTAMP,
            }
        )

    return payload


async def _extend_doc_subscription(db: firestore.Client, doc_ref: firestore.DocumentReference, days: int) -> None:
    transaction = db.transaction()

    @firestore.transactional
    def _run(transaction: firestore.Transaction) -> None:
        snapshot = doc_ref.get(transaction=transaction)
        data = snapshot.to_dict() or {}
        now = datetime.now(timezone.utc)
        current_end = as_utc_datetime(data.get("subscriptionEndsAt"))
        base = current_end if current_end and current_end > now else now
        transaction.set(
            doc_ref,
            {"subscriptionEndsAt": base + timedelta(days=days), "updatedAt": firestore.SERVER_TIMESTAMP},
            merge=True,
        )

    await asyncio.to_thread(_run, transaction)


async def save_vk_user(
    profile: VkProfile,
    referral_code: Optional[str] = None,
    group_id: Optional[int] = None,
) -> tuple[str, dict]:
    db = init_firebase()
    auth_uid = vk_uid(profile.id)
    auth_user = await asyncio.to_thread(ensure_vk_auth_user, auth_uid, profile)

    vk_ref = db.collection("vk_users").document(auth_uid)
    users_ref = db.collection("users")
    external_candidates = [auth_uid, str(profile.id)]

    vk_snapshot, user_docs = await asyncio.to_thread(
        lambda: (
            vk_ref.get(),
            users_ref.where("externalVk", "in", external_candidates).limit(1).get(),
        )
    )
    user_doc = user_docs[0] if user_docs else None
    user_uid: str
    user_data: dict
    is_new_user = user_doc is None
    if is_new_user:
        user_uid = str(uuid.uuid4())
        user_ref = users_ref.document(user_uid)
        user_exists = False
        user_data = {}
    else:
        user_data = user_doc.to_dict() or {}
        stored_uid = user_data.get("uid")
        if isinstance(stored_uid, str) and _is_uuid(stored_uid):
            user_uid = stored_uid
        elif _is_uuid(user_doc.id):
            user_uid = user_doc.id
        else:
            user_uid = str(uuid.uuid4())
        user_ref = user_doc.reference
        user_exists = True

    batch = db.batch()
    batch.set(
        vk_ref,
        _vk_users_mirror_payload(
            auth_uid,
            profile,
            auth_user,
            vk_snapshot.exists,
            group_id=group_id,
        ),
        merge=True,
    )
    batch.set(
        user_ref,
        _vk_users_document_payload(
            user_uid,
            profile,
            auth_user,
            user_exists,
            user_data,
            referral_code=referral_code if is_new_user else None,
            group_id=group_id,
        ),
        merge=True,
    )
    await asyncio.to_thread(batch.commit)

    if is_new_user and referral_code:
        await _apply_referral_join_bonus(db, referral_code, user_ref)

    saved_snapshot = await asyncio.to_thread(user_ref.get)
    saved_data = saved_snapshot.to_dict() or {}
    saved_data = await _ensure_remnawave_user(user_uid, saved_data)
    return user_uid, saved_data


async def save_telegram_user(tg_user: User, referral_code: Optional[str] = None) -> tuple[str, dict]:
    db = init_firebase()
    auth_uid = telegram_uid(tg_user.id)
    auth_user = await asyncio.to_thread(ensure_auth_user, auth_uid, tg_user)

    telegram_ref = db.collection("telegram_users").document(auth_uid)
    users_ref = db.collection("users")
    external_tg_candidates = [auth_uid, str(tg_user.id)]

    telegram_snapshot, user_docs = await asyncio.to_thread(
        lambda: (
            telegram_ref.get(),
            users_ref.where("externalTg", "in", external_tg_candidates)
            .limit(1)
            .get(),
        )
    )
    user_doc = user_docs[0] if user_docs else None
    user_uid: str
    user_data: dict
    is_new_user = user_doc is None
    if is_new_user:
        user_uid = str(uuid.uuid4())
        user_ref = users_ref.document(user_uid)
        user_exists = False
        user_data = {}
    else:
        user_data = user_doc.to_dict() or {}
        stored_uid = user_data.get("uid")
        if isinstance(stored_uid, str) and _is_uuid(stored_uid):
            user_uid = stored_uid
        elif _is_uuid(user_doc.id):
            user_uid = user_doc.id
        else:
            user_uid = str(uuid.uuid4())
        user_ref = user_doc.reference
        user_exists = True

    batch = db.batch()
    batch.set(
        telegram_ref,
        _telegram_payload(auth_uid, tg_user, auth_user, telegram_snapshot.exists),
        merge=True,
    )
    batch.set(
        user_ref,
        _users_payload(user_uid, tg_user, auth_user, user_exists, user_data,
                       referral_code if is_new_user else None),
        merge=True,
    )
    await asyncio.to_thread(batch.commit)

    if is_new_user and referral_code:
        await _apply_referral_join_bonus(db, referral_code, user_ref)

    saved_snapshot = await asyncio.to_thread(user_ref.get)
    saved_data = saved_snapshot.to_dict() or {}
    saved_data = await _ensure_remnawave_user(
        user_uid, saved_data, telegram_id=tg_user.id
    )
    return user_uid, saved_data


async def extend_subscription(tg_user: User, days: int) -> tuple[str, dict]:
    uid, _ = await save_telegram_user(tg_user)
    db = init_firebase()
    auth_uid = telegram_uid(tg_user.id)
    users_ref = db.collection("users")

    def extend() -> dict:
        docs = (
            users_ref.where("externalTg", "in", [auth_uid, str(tg_user.id)])
            .limit(1)
            .get()
        )
        if not docs:
            raise RuntimeError("Telegram user was not found")

        doc_ref = docs[0].reference
        transaction = db.transaction()

        @firestore.transactional
        def _run(transaction: firestore.Transaction) -> dict:
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() or {}
            now = datetime.now(timezone.utc)
            current_end = as_utc_datetime(data.get("subscriptionEndsAt"))
            base = current_end if current_end and current_end > now else now
            payload = {
                "subscriptionEndsAt": base + timedelta(days=days),
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
            transaction.set(doc_ref, payload, merge=True)
            return {**data, **payload}

        return _run(transaction)

    data = await asyncio.to_thread(extend)
    end = as_utc_datetime(data.get("subscriptionEndsAt"))
    await _update_remnawave_subscription(uid, end)
    return uid, data


async def extend_subscription_vk(
    profile: VkProfile,
    days: int,
    group_id: Optional[int] = None,
) -> tuple[str, dict]:
    uid, _ = await save_vk_user(profile, group_id=group_id)
    db = init_firebase()
    auth_uid = vk_uid(profile.id)
    users_ref = db.collection("users")

    def extend() -> dict:
        docs = (
            users_ref.where("externalVk", "in", [auth_uid, str(profile.id)])
            .limit(1)
            .get()
        )
        if not docs:
            raise RuntimeError("VK user was not found")

        doc_ref = docs[0].reference
        transaction = db.transaction()

        @firestore.transactional
        def _run(transaction: firestore.Transaction) -> dict:
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() or {}
            now = datetime.now(timezone.utc)
            current_end = as_utc_datetime(data.get("subscriptionEndsAt"))
            base = current_end if current_end and current_end > now else now
            payload = {
                "subscriptionEndsAt": base + timedelta(days=days),
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
            transaction.set(doc_ref, payload, merge=True)
            return {**data, **payload}

        return _run(transaction)

    data = await asyncio.to_thread(extend)
    end = as_utc_datetime(data.get("subscriptionEndsAt"))
    await _update_remnawave_subscription(uid, end)
    return uid, data


async def extend_subscription_with_tier(
    tg_user: User, plan_key: str
) -> tuple[str, dict]:
    """Extend subscription with tier awareness.

    - Premium: stores tier, resets from now if upgrading from standart.
    - Standart: standard extend from max(now, end).
    """
    plan = SUBSCRIPTION_PLANS.get(plan_key)
    if plan is None:
        raise ValueError(f"Unknown plan key: {plan_key}")

    days = plan["days"]
    tier = plan.get("tier", "standart")
    uid, _ = await save_telegram_user(tg_user)
    db = init_firebase()
    auth_uid = telegram_uid(tg_user.id)
    users_ref = db.collection("users")

    def extend() -> dict:
        docs = (
            users_ref.where("externalTg", "in", [auth_uid, str(tg_user.id)])
            .limit(1)
            .get()
        )
        if not docs:
            raise RuntimeError("Telegram user was not found")

        doc_ref = docs[0].reference
        transaction = db.transaction()

        @firestore.transactional
        def _run(transaction: firestore.Transaction) -> dict:
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() or {}
            now = datetime.now(timezone.utc)
            current_end = as_utc_datetime(data.get("subscriptionEndsAt"))
            current_tier = data.get("subscriptionTier")

            # If upgrading from standart to premium, reset from now
            if tier == "premium" and current_tier == "standart":
                base = now
            else:
                base = current_end if current_end and current_end > now else now

            payload = {
                "subscriptionEndsAt": base + timedelta(days=days),
                "subscriptionTier": tier,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
            transaction.set(doc_ref, payload, merge=True)
            return {**data, **payload}

        return _run(transaction)

    data = await asyncio.to_thread(extend)
    end = as_utc_datetime(data.get("subscriptionEndsAt"))
    await _update_remnawave_subscription(uid, end, tier=tier)
    return uid, data


async def extend_subscription_vk_with_tier(
    profile: VkProfile,
    plan_key: str,
    group_id: Optional[int] = None,
) -> tuple[str, dict]:
    """Extend VK subscription with tier awareness."""
    plan = SUBSCRIPTION_PLANS.get(plan_key)
    if plan is None:
        raise ValueError(f"Unknown plan key: {plan_key}")

    days = plan["days"]
    tier = plan.get("tier", "standart")
    uid, _ = await save_vk_user(profile, group_id=group_id)
    db = init_firebase()
    auth_uid = vk_uid(profile.id)
    users_ref = db.collection("users")

    def extend() -> dict:
        docs = (
            users_ref.where("externalVk", "in", [auth_uid, str(profile.id)])
            .limit(1)
            .get()
        )
        if not docs:
            raise RuntimeError("VK user was not found")

        doc_ref = docs[0].reference
        transaction = db.transaction()

        @firestore.transactional
        def _run(transaction: firestore.Transaction) -> dict:
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() or {}
            now = datetime.now(timezone.utc)
            current_end = as_utc_datetime(data.get("subscriptionEndsAt"))
            current_tier = data.get("subscriptionTier")

            # If upgrading from standart to premium, reset from now
            if tier == "premium" and current_tier == "standart":
                base = now
            else:
                base = current_end if current_end and current_end > now else now

            payload = {
                "subscriptionEndsAt": base + timedelta(days=days),
                "subscriptionTier": tier,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
            transaction.set(doc_ref, payload, merge=True)
            return {**data, **payload}

        return _run(transaction)

    data = await asyncio.to_thread(extend)
    end = as_utc_datetime(data.get("subscriptionEndsAt"))
    await _update_remnawave_subscription(uid, end, tier=tier)
    return uid, data


async def grant_lifetime_subscription_tg(tg_id: int) -> None:
    db = init_firebase()
    auth_uid = telegram_uid(tg_id)
    users_ref = db.collection("users")
    user_docs = await asyncio.to_thread(
        lambda: users_ref.where("externalTg", "in", [auth_uid, str(tg_id)])
        .limit(1)
        .get()
    )
    if not user_docs:
        return
    user_ref = user_docs[0].reference
    lifetime_date = datetime(2099, 1, 1, tzinfo=timezone.utc)
    await asyncio.to_thread(
        lambda: user_ref.update({
            "subscriptionEndsAt": lifetime_date,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        })
    )
    data = user_docs[0].to_dict() or {}
    user_uid = data.get("uid") or user_docs[0].id
    await _update_remnawave_subscription(user_uid, lifetime_date)


async def grant_lifetime_subscription_vk(vk_id: int) -> None:
    db = init_firebase()
    auth_uid = vk_uid(vk_id)
    users_ref = db.collection("users")
    user_docs = await asyncio.to_thread(
        lambda: users_ref.where("externalVk", "in", [auth_uid, str(vk_id)])
        .limit(1)
        .get()
    )
    if not user_docs:
        return
    user_ref = user_docs[0].reference
    lifetime_date = datetime(2099, 1, 1, tzinfo=timezone.utc)
    await asyncio.to_thread(
        lambda: user_ref.update({
            "subscriptionEndsAt": lifetime_date,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        })
    )
    data = user_docs[0].to_dict() or {}
    user_uid = data.get("uid") or user_docs[0].id
    await _update_remnawave_subscription(user_uid, lifetime_date)
