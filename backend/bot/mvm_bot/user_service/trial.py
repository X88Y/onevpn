import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram.types import User  # type: ignore[import-not-found]
from firebase_admin import firestore  # type: ignore[import-not-found,import-untyped]

from mvm_bot.constants import TRIAL_DAYS, TRIAL_FIELDS
from mvm_bot.datetime_utils import as_utc_datetime
from mvm_bot.firebase_client import init_firebase
from mvm_bot.user_service.helpers import VkProfile, telegram_uid, vk_uid
from mvm_bot.user_service.remnawave import _update_remnawave_subscription


def _initial_trial_fields() -> dict:
    return {
        "subscriptionEndsAt": None,
        "isTelegramTrialActivated": False,
        "isAppleTrialActivated": False,
        "isVkTrialActivated": False,
    }


def _missing_trial_defaults(data: dict) -> dict:
    payload = {}
    for key, value in _initial_trial_fields().items():
        if key not in data:
            payload[key] = value

    return payload


def _connected_trial_providers(data: dict) -> list[str]:
    providers = []
    if data.get("externalTg"):
        providers.append("tg")
    if data.get("externalAppleId"):
        providers.append("apple")
    if data.get("externalVk"):
        providers.append("vk")

    return providers


def _build_trial_activation_payload(data: dict) -> tuple[dict, list[str]]:
    activated = [
        provider
        for provider in _connected_trial_providers(data)
        if data.get(TRIAL_FIELDS[provider]) is not True
    ]
    payload = _missing_trial_defaults(data)
    if not activated:
        return payload, activated

    now = datetime.now(timezone.utc)
    current_end = as_utc_datetime(data.get("subscriptionEndsAt"))
    base = current_end if current_end and current_end > now else now
    payload["subscriptionEndsAt"] = base + timedelta(days=TRIAL_DAYS * len(activated))
    payload["trialActivatedAt"] = now
    for provider in activated:
        payload[TRIAL_FIELDS[provider]] = True

    return payload, activated


async def start_telegram_trial(tg_user: User) -> tuple[str, dict, list[str]]:
    from mvm_bot.user_service.core import save_telegram_user

    uid, _ = await save_telegram_user(tg_user)
    db = init_firebase()
    auth_uid = telegram_uid(tg_user.id)
    users_ref = db.collection("users")

    def activate() -> tuple[dict, list[str]]:
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
        def update_in_transaction(transaction: firestore.Transaction) -> tuple[dict, list[str]]:
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() or {}
            payload, activated = _build_trial_activation_payload(data)
            if payload:
                payload["updatedAt"] = firestore.SERVER_TIMESTAMP
                transaction.set(doc_ref, payload, merge=True)
            return {**data, **payload}, activated

        return update_in_transaction(transaction)

    data, activated = await asyncio.to_thread(activate)
    end = as_utc_datetime(data.get("subscriptionEndsAt"))
    await _update_remnawave_subscription(uid, end)
    return uid, data, activated


async def start_vk_trial(
    profile: VkProfile,
    group_id: Optional[int] = None,
) -> tuple[str, dict, list[str]]:
    from mvm_bot.user_service.core import save_vk_user

    uid, _ = await save_vk_user(profile, group_id=group_id)
    db = init_firebase()
    auth_uid = vk_uid(profile.id)
    users_ref = db.collection("users")

    def activate() -> tuple[dict, list[str]]:
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
        def update_in_transaction(
            transaction: firestore.Transaction,
        ) -> tuple[dict, list[str]]:
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() or {}
            payload, activated = _build_trial_activation_payload(data)
            if payload:
                payload["updatedAt"] = firestore.SERVER_TIMESTAMP
                transaction.set(doc_ref, payload, merge=True)
            return {**data, **payload}, activated

        return update_in_transaction(transaction)

    data, activated = await asyncio.to_thread(activate)
    end = as_utc_datetime(data.get("subscriptionEndsAt"))
    await _update_remnawave_subscription(uid, end)
    return uid, data, activated
