import asyncio
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from aiogram.types import User  # type: ignore[import-not-found]
from firebase_admin import auth, firestore  # type: ignore[import-not-found,import-untyped]

from mvm_bot.constants import REFERRAL_BONUS_DAYS, TRIAL_DAYS, TRIAL_FIELDS
from mvm_bot.datetime_utils import as_utc_datetime
from mvm_bot.firebase_client import init_firebase


def telegram_uid(tg_id: int) -> str:
    return f"tg:{tg_id}"


def vk_uid(vk_id: int) -> str:
    return f"vk:{vk_id}"


def record_payment_checkout_click(
    *,
    service: str,
    provider: str,
    external_user_id: str,
    plan_key: str,
    amount: float,
    currency: str,
    pay_url: str,
    channel: str,
    correlation_id: str | None = None,
    payment_method: str | None = None,
    payment_system: int | None = None,
) -> None:
    """Append one Firestore document per generated external pay link (user tap)."""
    payload: dict[str, Any] = {
        "service": service,
        "provider": provider,
        "externalUserId": external_user_id,
        "planKey": plan_key,
        "amount": amount,
        "currency": currency,
        "payUrl": pay_url,
        "channel": channel,
        "createdAt": firestore.SERVER_TIMESTAMP,
    }
    if correlation_id is not None:
        payload["correlationId"] = correlation_id
    if payment_method is not None:
        payload["paymentMethod"] = payment_method
    if payment_system is not None:
        payload["paymentSystem"] = payment_system

    db = init_firebase()
    db.collection("payment_checkout_clicks").add(payload)


@dataclass
class VkProfile:
    id: int
    first_name: str
    last_name: Optional[str]
    screen_name: Optional[str]


def _display_name_vk(profile: VkProfile) -> str:
    full_name = " ".join(
        part for part in [profile.first_name, profile.last_name] if part
    )
    if full_name:
        return full_name
    if profile.screen_name:
        return profile.screen_name
    return f"VK user {profile.id}"


def generate_referral_code() -> str:
    return secrets.token_hex(4)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False

    return True


def _display_name(tg_user: User) -> str:
    full_name = " ".join(
        part for part in [tg_user.first_name, tg_user.last_name] if part
    )
    if full_name:
        return full_name

    if tg_user.username:
        return f"@{tg_user.username}"

    return f"Telegram user {tg_user.id}"


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
    for provider in activated:
        payload[TRIAL_FIELDS[provider]] = True

    return payload, activated


def ensure_auth_user(uid: str, tg_user: User) -> auth.UserRecord:
    try:
        user = auth.get_user(uid)
    except auth.UserNotFoundError:
        user = auth.create_user(
            uid=uid,
            display_name=_display_name(tg_user),
        )

    auth.set_custom_user_claims(
        uid,
        {
            "provider": "telegram",
            "tgId": str(tg_user.id),
        },
    )
    return user


def ensure_vk_auth_user(uid: str, profile: VkProfile) -> auth.UserRecord:
    try:
        user = auth.get_user(uid)
    except auth.UserNotFoundError:
        user = auth.create_user(
            uid=uid,
            display_name=_display_name_vk(profile),
        )

    auth.set_custom_user_claims(
        uid,
        {
            "provider": "vk",
            "vkId": str(profile.id),
        },
    )
    return user


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
) -> dict:
    current_data = current_data or {}
    payload = {
        "externalVk": vk_uid(profile.id),
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


async def _apply_referral_join_bonus(
    db: firestore.Client,
    referral_code: str,
    new_user_ref: firestore.DocumentReference,
) -> None:
    users_ref = db.collection("users")
    referrer_docs = await asyncio.to_thread(
        lambda: users_ref.where("referralCode", "==", referral_code).limit(1).get()
    )
    if not referrer_docs:
        return

    referrer_ref = referrer_docs[0].reference
    # Avoid self-referral (same document)
    if referrer_ref.id == new_user_ref.id:
        return

    await _extend_doc_subscription(db, referrer_ref, REFERRAL_BONUS_DAYS)
    await _extend_doc_subscription(db, new_user_ref, REFERRAL_BONUS_DAYS)


async def grant_purchase_referral_bonus_tg(tg_user: User) -> bool:
    """Grant +REFERRAL_BONUS_DAYS to the referrer when a referred Telegram user makes a purchase."""
    db = init_firebase()
    auth_uid = telegram_uid(tg_user.id)
    users_ref = db.collection("users")

    user_docs = await asyncio.to_thread(
        lambda: users_ref.where("externalTg", "in", [auth_uid, str(tg_user.id)]).limit(1).get()
    )
    if not user_docs:
        return False

    referred_by_code = (user_docs[0].to_dict() or {}).get("referredByCode")
    if not referred_by_code:
        return False

    referrer_docs = await asyncio.to_thread(
        lambda: users_ref.where("referralCode", "==", referred_by_code).limit(1).get()
    )
    if not referrer_docs:
        return False

    await _extend_doc_subscription(db, referrer_docs[0].reference, REFERRAL_BONUS_DAYS)
    return True


async def count_referrals(referral_code: str) -> int:
    """Return the number of users who registered using this referral code."""
    db = init_firebase()
    docs = await asyncio.to_thread(
        lambda: db.collection("users")
        .where("referredByCode", "==", referral_code)
        .select([])
        .get()
    )
    return len(docs)


async def apply_referral_code_tg(tg_user: User, referral_code: str) -> tuple[bool, str]:
    """Apply a referral code manually for an existing Telegram user."""
    db = init_firebase()
    auth_uid = telegram_uid(tg_user.id)
    users_ref = db.collection("users")

    user_docs = await asyncio.to_thread(
        lambda: users_ref.where("externalTg", "in", [auth_uid, str(tg_user.id)]).limit(1).get()
    )
    if not user_docs:
        return False, "Пользователь не найден."

    user_doc = user_docs[0]
    user_data = user_doc.to_dict() or {}
    user_ref = user_doc.reference

    if user_data.get("referredByCode"):
        return False, "Вы уже использовали реферальный код."

    referrer_docs = await asyncio.to_thread(
        lambda: users_ref.where("referralCode", "==", referral_code).limit(1).get()
    )
    if not referrer_docs:
        return False, "Реферальный код не найден. Проверьте и попробуйте снова."

    referrer_ref = referrer_docs[0].reference
    if referrer_ref.id == user_ref.id:
        return False, "Нельзя использовать собственный код."

    await asyncio.to_thread(
        lambda: user_ref.update(
            {"referredByCode": referral_code, "updatedAt": firestore.SERVER_TIMESTAMP}
        )
    )
    await _extend_doc_subscription(db, referrer_ref, REFERRAL_BONUS_DAYS)
    await _extend_doc_subscription(db, user_ref, REFERRAL_BONUS_DAYS)
    return True, f"Реферальный код принят! Вы и ваш друг получили +{REFERRAL_BONUS_DAYS} дня к подписке. 🎉"


async def apply_referral_code_vk(profile: VkProfile, referral_code: str) -> tuple[bool, str]:
    """Apply a referral code manually for an existing VK user."""
    db = init_firebase()
    auth_uid = vk_uid(profile.id)
    users_ref = db.collection("users")

    user_docs = await asyncio.to_thread(
        lambda: users_ref.where("externalVk", "in", [auth_uid, str(profile.id)]).limit(1).get()
    )
    if not user_docs:
        return False, "Пользователь не найден."

    user_doc = user_docs[0]
    user_data = user_doc.to_dict() or {}
    user_ref = user_doc.reference

    if user_data.get("referredByCode"):
        return False, "Вы уже использовали реферальный код."

    referrer_docs = await asyncio.to_thread(
        lambda: users_ref.where("referralCode", "==", referral_code).limit(1).get()
    )
    if not referrer_docs:
        return False, "Реферальный код не найден. Проверьте и попробуйте снова."

    referrer_ref = referrer_docs[0].reference
    if referrer_ref.id == user_ref.id:
        return False, "Нельзя использовать собственный код."

    await asyncio.to_thread(
        lambda: user_ref.update(
            {"referredByCode": referral_code, "updatedAt": firestore.SERVER_TIMESTAMP}
        )
    )
    await _extend_doc_subscription(db, referrer_ref, REFERRAL_BONUS_DAYS)
    await _extend_doc_subscription(db, user_ref, REFERRAL_BONUS_DAYS)
    return True, f"Реферальный код принят! Вы и ваш друг получили +{REFERRAL_BONUS_DAYS} дня к подписке. 🎉"


async def save_vk_user(profile: VkProfile, referral_code: Optional[str] = None) -> tuple[str, dict]:
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
        _vk_users_mirror_payload(auth_uid, profile, auth_user, vk_snapshot.exists),
        merge=True,
    )
    batch.set(
        user_ref,
        _vk_users_document_payload(
            user_uid, profile, auth_user, user_exists, user_data,
            referral_code if is_new_user else None,
        ),
        merge=True,
    )
    await asyncio.to_thread(batch.commit)

    if is_new_user and referral_code:
        await _apply_referral_join_bonus(db, referral_code, user_ref)

    saved_snapshot = await asyncio.to_thread(user_ref.get)
    saved_data = saved_snapshot.to_dict() or {}
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
    return uid, data


async def start_telegram_trial(tg_user: User) -> tuple[str, dict, list[str]]:
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
    return uid, data, activated


async def extend_subscription_vk(profile: VkProfile, days: int) -> tuple[str, dict]:
    uid, _ = await save_vk_user(profile)
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
    return uid, data


async def start_vk_trial(profile: VkProfile) -> tuple[str, dict, list[str]]:
    uid, _ = await save_vk_user(profile)
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
    return uid, data, activated
