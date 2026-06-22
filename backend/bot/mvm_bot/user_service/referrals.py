import asyncio
import logging

from aiogram.types import User  # type: ignore[import-not-found]
from firebase_admin import firestore  # type: ignore[import-not-found,import-untyped]

from mvm_bot.constants import REFERRAL_BONUS_DAYS, REFERRAL_PURCHASE_BONUS_DAYS
from mvm_bot.firebase_client import init_firebase
from mvm_bot.user_service.helpers import VkProfile, telegram_uid, vk_uid
from mvm_bot.user_service.notifications import notify_referrer
from mvm_bot.user_service.subscription_tx import extend_doc_subscription as _extend_doc_subscription

logger = logging.getLogger(__name__)


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

    try:
        referrer_data = referrer_docs[0].to_dict() or {}
        await notify_referrer(
            referrer_data,
            f"По вашей реферальной ссылке зарегистрировался новый пользователь! Вам и вашему другу начислено по +{REFERRAL_BONUS_DAYS} дня подписки. 🎉"
        )
    except Exception:
        logger.exception("Failed to notify referrer on join bonus")


async def grant_purchase_referral_bonus_tg(tg_user: User) -> bool:
    """Grant +REFERRAL_PURCHASE_BONUS_DAYS to the referrer when a referred Telegram user makes a purchase."""
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

    await _extend_doc_subscription(db, referrer_docs[0].reference, REFERRAL_PURCHASE_BONUS_DAYS)

    try:
        referrer_data = referrer_docs[0].to_dict() or {}
        await notify_referrer(
            referrer_data,
            f"Друг, зарегистрировавшийся по вашей реферальной ссылке, совершил покупку! Вам начислено +{REFERRAL_PURCHASE_BONUS_DAYS} дней подписки. 🎉"
        )
    except Exception:
        logger.exception("Failed to notify referrer on purchase bonus")

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

    try:
        referrer_data = referrer_docs[0].to_dict() or {}
        await notify_referrer(
            referrer_data,
            f"По вашей реферальной ссылке зарегистрировался новый пользователь! Вам и вашему другу начислено по +{REFERRAL_BONUS_DAYS} дня подписки. 🎉"
        )
    except Exception:
        logger.exception("Failed to notify referrer on join bonus")

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

    try:
        referrer_data = referrer_docs[0].to_dict() or {}
        await notify_referrer(
            referrer_data,
            f"По вашей реферальной ссылке зарегистрировался новый пользователь! Вам и вашему другу начислено по +{REFERRAL_BONUS_DAYS} дня подписки. 🎉"
        )
    except Exception:
        logger.exception("Failed to notify referrer on join bonus")

    return True, f"Реферальный код принят! Вы и ваш друг получили +{REFERRAL_BONUS_DAYS} дня к подписке. 🎉"
