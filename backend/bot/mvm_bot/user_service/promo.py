import asyncio
import logging
from datetime import datetime, timezone

from firebase_admin import firestore
from aiogram.types import User
from mvm_bot.firebase_client import init_firebase
from mvm_bot.user_service.helpers import VkProfile, telegram_uid, vk_uid

logger = logging.getLogger(__name__)

DEFAULT_PROMO_CODES = {"MVM40", "PROMO40", "WELCOME40", "START40", "SALE40"}
PROMOCODES_COLLECTION = "promocodes"

_PROMO_OK = "ok"
_PROMO_INVALID = "invalid"
_PROMO_ALREADY = "already"
_PROMO_LIMIT = "limit"
_PROMO_EXPIRED = "expired"
_PROMO_PURCHASED = "purchased"


def _parse_non_negative_int(value: object) -> int | None:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _coerce_utc_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif hasattr(value, "to_datetime") and callable(getattr(value, "to_datetime")):
        try:
            dt = value.to_datetime()  # type: ignore[assignment]
        except Exception:
            return None
    elif isinstance(value, str):
        normalized = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _promo_is_expired(valid_until: object) -> bool:
    valid_until_dt = _coerce_utc_datetime(valid_until)
    if valid_until_dt is None:
        return False
    return datetime.now(timezone.utc) >= valid_until_dt


def _extract_used_promo_codes(user_data: dict) -> set[str]:
    used_codes: set[str] = set()
    raw_used_codes = user_data.get("usedPromoCodes")
    if isinstance(raw_used_codes, (list, tuple, set)):
        for item in raw_used_codes:
            if isinstance(item, str):
                normalized = item.strip().upper()
                if normalized:
                    used_codes.add(normalized)

    legacy_code = user_data.get("activatedPromoCode")
    if isinstance(legacy_code, str):
        normalized = legacy_code.strip().upper()
        if normalized:
            used_codes.add(normalized)
    return used_codes


def _activate_promo_transactional(*, db, user_ref, code_upper: str) -> tuple[str, float]:
    promo_ref = db.collection(PROMOCODES_COLLECTION).document(code_upper)
    transaction = db.transaction()

    @firestore.transactional
    def _run(transaction_obj):
        user_snapshot = user_ref.get(transaction=transaction_obj)
        user_data = user_snapshot.to_dict() or {}
        if user_data.get("hasSuccessfulPurchase") is True:
            return _PROMO_PURCHASED, 0.0

        used_codes = _extract_used_promo_codes(user_data)
        if code_upper in used_codes:
            return _PROMO_ALREADY, 0.0

        promo_snapshot = promo_ref.get(transaction=transaction_obj)
        if promo_snapshot.exists:
            promo_data = promo_snapshot.to_dict() or {}
            if not promo_data.get("isActive", True):
                return _PROMO_INVALID, 0.0
            if _promo_is_expired(promo_data.get("validUntil")):
                return _PROMO_EXPIRED, 0.0

            max_uses = _parse_non_negative_int(promo_data.get("maxUses"))
            uses_count = _parse_non_negative_int(promo_data.get("usesCount")) or 0
            if max_uses is not None and uses_count >= max_uses:
                return _PROMO_LIMIT, 0.0

            discount = float(promo_data.get("discount", 0.4))
            transaction_obj.set(
                promo_ref,
                {
                    "usesCount": uses_count + 1,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
        elif code_upper in DEFAULT_PROMO_CODES:
            discount = 0.4
        else:
            return _PROMO_INVALID, 0.0

        transaction_obj.set(
            user_ref,
            {
                "promoActivated": True,
                "activatedPromoCode": code_upper,
                "promoDiscount": discount,
                "usedPromoCodes": sorted((*used_codes, code_upper)),
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        return _PROMO_OK, discount

    return _run(transaction)

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
        doc = await asyncio.to_thread(
            db.collection(PROMOCODES_COLLECTION).document(code_upper).get
        )
        if doc.exists:
            data = doc.to_dict() or {}
            discount = data.get("discount", 0.4)  # default to 40%
            max_uses = _parse_non_negative_int(data.get("maxUses"))
            uses_count = _parse_non_negative_int(data.get("usesCount")) or 0
            if (
                data.get("isActive", True)
                and not _promo_is_expired(data.get("validUntil"))
                and (max_uses is None or uses_count < max_uses)
            ):
                return True, float(discount)
    except Exception:
        logger.exception(
            f"Failed to fetch promo code {code_upper} from Firestore, falling back to local codes"
        )

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

    if user_data.get("hasSuccessfulPurchase") is True:
        return False, "Промокод можно использовать только до первой покупки."

    code_upper = code.strip().upper()
    status, discount = await asyncio.to_thread(
        _activate_promo_transactional,
        db=db,
        user_ref=user_ref,
        code_upper=code_upper,
    )
    if status == _PROMO_ALREADY:
        return False, "Этот промокод уже был активирован."
    if status == _PROMO_LIMIT:
        return False, "Лимит активаций этого промокода исчерпан."
    if status == _PROMO_EXPIRED:
        return False, "Срок действия промокода истек."
    if status == _PROMO_PURCHASED:
        return False, "Промокод можно использовать только до первой покупки."
    if status != _PROMO_OK:
        return False, "Неверный или неактивный промокод."

    discount_percent = int(discount * 100)
    return True, f"Промокод активирован✅\n\nСкидка на первую покупку {discount_percent}%🥳"

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

    if user_data.get("hasSuccessfulPurchase") is True:
        return False, "Промокод можно использовать только до первой покупки."

    code_upper = code.strip().upper()
    status, discount = await asyncio.to_thread(
        _activate_promo_transactional,
        db=db,
        user_ref=user_ref,
        code_upper=code_upper,
    )
    if status == _PROMO_ALREADY:
        return False, "Этот промокод уже был активирован."
    if status == _PROMO_LIMIT:
        return False, "Лимит активаций этого промокода исчерпан."
    if status == _PROMO_EXPIRED:
        return False, "Срок действия промокода истек."
    if status == _PROMO_PURCHASED:
        return False, "Промокод можно использовать только до первой покупки."
    if status != _PROMO_OK:
        return False, "Неверный или неактивный промокод."

    discount_percent = int(discount * 100)
    return True, f"Промокод активирован✅\n\nСкидка на первую покупку {discount_percent}%🥳"
