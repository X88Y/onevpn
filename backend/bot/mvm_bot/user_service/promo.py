import asyncio
import logging
from firebase_admin import firestore
from aiogram.types import User
from mvm_bot.firebase_client import init_firebase
from mvm_bot.user_service.helpers import VkProfile, telegram_uid, vk_uid

logger = logging.getLogger(__name__)

DEFAULT_PROMO_CODES = {"MVM40", "PROMO40", "WELCOME40", "START40", "SALE40"}

async def check_promo_code_validity(code: str) -> tuple[bool, float]:
    """
    Checks if a promo code is valid.
    Returns (is_valid, discount_percent).
    discount_percent is e.g. 0.40 for 40% discount.
    """
    code_upper = code.strip().upper()
    db = init_firebase()
    
    # Try querying Firestore
    try:
        doc = await asyncio.to_thread(db.collection("promocodes").document(code_upper).get)
        if doc.exists:
            data = doc.to_dict() or {}
            is_active = data.get("isActive", True)
            discount = data.get("discount", 0.4) # default to 40%
            if is_active:
                return True, float(discount)
    except Exception:
        logger.exception(f"Failed to fetch promo code {code_upper} from Firestore, falling back to local codes")

    # Local fallback
    if code_upper in DEFAULT_PROMO_CODES:
        return True, 0.4
        
    return False, 0.0

async def apply_promo_code_tg(tg_user: User, code: str) -> tuple[bool, str]:
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

    if user_data.get("promoActivated"):
        return False, "Вы уже активировали промокод."

    is_valid, discount = await check_promo_code_validity(code)
    if not is_valid:
        return False, "Неверный или неактивный промокод."

    discount_percent = int(discount * 100)
    
    await asyncio.to_thread(
        lambda: user_ref.update({
            "promoActivated": True,
            "activatedPromoCode": code.strip().upper(),
            "promoDiscount": discount,
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
    )

    return True, f"Промокод активирован✅\n\nСкидка на все тарифы {discount_percent}%🥳"

async def apply_promo_code_vk(profile: VkProfile, code: str) -> tuple[bool, str]:
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

    if user_data.get("promoActivated"):
        return False, "Вы уже активировали промокод."

    is_valid, discount = await check_promo_code_validity(code)
    if not is_valid:
        return False, "Неверный или неактивный промокод."

    discount_percent = int(discount * 100)

    await asyncio.to_thread(
        lambda: user_ref.update({
            "promoActivated": True,
            "activatedPromoCode": code.strip().upper(),
            "promoDiscount": discount,
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
    )

    return True, f"Промокод активирован✅\n\nСкидка на все тарифы {discount_percent}%🥳"
