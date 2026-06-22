import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from firebase_admin import firestore

from bot_admin.config import admin_telegram_ids
from bot_admin.constants import PROMOCODES_COLLECTION
from bot_admin.firebase_client import init_firestore

logger = logging.getLogger(__name__)
router = Router(name="promocodes")

KEEP_EXISTING = object()
INVALID_VALUE = object()


class CreatePromocode(StatesGroup):
    code = State()
    discount_percent = State()
    max_uses = State()
    valid_until = State()


def _is_admin(user_id: Optional[int]) -> bool:
    if user_id is None:
        return False
    return user_id in admin_telegram_ids()


def _parse_discount_percent(raw: str) -> Optional[float]:
    cleaned = raw.strip().replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if value <= 0 or value > 100:
        return None
    return value


def _parse_max_uses(raw: str) -> int | None | object:
    cleaned = raw.strip().lower()
    if cleaned in {"skip"}:
        return KEEP_EXISTING
    if cleaned in {"", "none", "no", "unlimited", "limitless", "0", "-"}:
        return None
    try:
        value = int(cleaned)
    except ValueError:
        return INVALID_VALUE
    if value <= 0:
        return INVALID_VALUE
    return value


def _parse_valid_until(raw: str) -> datetime | None | object:
    cleaned = raw.strip()
    lowered = cleaned.lower()
    if lowered == "skip":
        return KEEP_EXISTING
    if lowered in {"", "none", "never", "0", "-"}:
        return None

    candidates = [cleaned, cleaned.replace(" ", "T")]
    for candidate in candidates:
        normalized = candidate.replace("z", "+00:00").replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed
    return INVALID_VALUE


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


def _format_valid_until(value: object) -> str:
    dt = _coerce_utc_datetime(value)
    if dt is None:
        return "none"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _format_promo_stats(code: str, data: dict) -> str:
    discount = float(data.get("discount", 0.0)) * 100
    is_active = bool(data.get("isActive", True))
    uses_count = int(data.get("usesCount", 0) or 0)
    max_uses_raw = data.get("maxUses")
    if max_uses_raw in (None, ""):
        max_uses = None
    else:
        try:
            max_uses = int(max_uses_raw)
        except (TypeError, ValueError):
            max_uses = None
    valid_until = _format_valid_until(data.get("validUntil"))
    if max_uses is None:
        usage_str = f"{uses_count}/∞"
        remaining = "∞"
    else:
        usage_str = f"{uses_count}/{max_uses}"
        remaining = str(max(0, max_uses - uses_count))
    return (
        f"<code>{code}</code> | discount=<b>{discount:g}%</b> | active={is_active}\n"
        f"uses={usage_str} | remaining={remaining}\n"
        f"validUntil={valid_until}"
    )


@router.message(Command("create_promocode"))
async def cmd_create_promocode(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return
    await state.clear()
    await state.set_state(CreatePromocode.code)
    await message.answer(
        "Step 1/4: send the promo code value.\n"
        "Example: <code>SUMMER40</code>\n"
        "Code will be uppercased and saved as Firestore document id.",
        parse_mode="HTML",
    )


@router.message(CreatePromocode.code, F.text)
async def create_promocode_step_code(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await state.clear()
        await message.answer("Access denied.")
        return
    raw_code = (message.text or "").strip()
    if not raw_code:
        await message.answer("Promo code cannot be empty.")
        return
    code = raw_code.upper()
    await state.update_data(promocode=code)
    await state.set_state(CreatePromocode.discount_percent)
    await message.answer(
        "Step 2/4: send discount percent (1..100).\n"
        "Examples: <code>40</code> or <code>15.5</code>.",
        parse_mode="HTML",
    )


@router.message(CreatePromocode.discount_percent, F.text)
async def create_promocode_step_discount(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await state.clear()
        await message.answer("Access denied.")
        return

    raw_discount = (message.text or "").strip()
    percent = _parse_discount_percent(raw_discount)
    if percent is None:
        await message.answer("Invalid discount percent. Send a number from 1 to 100.")
        return
    await state.update_data(discount_percent=percent)
    await state.set_state(CreatePromocode.max_uses)
    await message.answer(
        "Step 3/4: send max users for this code.\n"
        "Examples: <code>100</code>, <code>none</code> (unlimited), or <code>skip</code> (keep current on update).",
        parse_mode="HTML",
    )


@router.message(CreatePromocode.max_uses, F.text)
async def create_promocode_step_max_uses(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await state.clear()
        await message.answer("Access denied.")
        return

    parsed = _parse_max_uses((message.text or "").strip())
    if parsed is INVALID_VALUE:
        await message.answer(
            "Invalid value. Send a positive integer, <code>none</code>, or <code>skip</code>.",
            parse_mode="HTML",
        )
        return

    await state.update_data(max_uses=parsed)
    await state.set_state(CreatePromocode.valid_until)
    await message.answer(
        "Step 4/4: send promo expiry in UTC.\n"
        "Examples: <code>2026-12-31T23:59</code>, <code>2026-12-31 23:59</code>, "
        "<code>none</code> (no expiry), or <code>skip</code> (keep current on update).",
        parse_mode="HTML",
    )


@router.message(CreatePromocode.valid_until, F.text)
async def create_promocode_step_valid_until(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await state.clear()
        await message.answer("Access denied.")
        return

    parsed_valid_until = _parse_valid_until((message.text or "").strip())
    if parsed_valid_until is INVALID_VALUE:
        await message.answer(
            "Invalid datetime format. Use <code>YYYY-MM-DD HH:MM</code>, "
            "<code>YYYY-MM-DDTHH:MM</code>, <code>none</code>, or <code>skip</code>.",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    code = str(data.get("promocode") or "").strip().upper()
    if not code:
        await state.clear()
        await message.answer("Session expired. Run /create_promocode again.")
        return

    percent = data.get("discount_percent")
    if not isinstance(percent, (int, float)):
        await state.clear()
        await message.answer("Session expired. Run /create_promocode again.")
        return
    max_uses = data.get("max_uses", KEEP_EXISTING)

    discount_fraction = round(percent / 100.0, 4)

    db = init_firestore()
    doc_ref = db.collection(PROMOCODES_COLLECTION).document(code)
    snapshot = doc_ref.get()
    existed = snapshot.exists

    payload = {
        "discount": discount_fraction,
        "isActive": True,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if not existed:
        payload["usesCount"] = 0
    if not existed:
        payload["createdAt"] = firestore.SERVER_TIMESTAMP

    if max_uses is not KEEP_EXISTING:
        if max_uses is None:
            payload["maxUses"] = firestore.DELETE_FIELD
        else:
            payload["maxUses"] = max_uses

    if parsed_valid_until is not KEEP_EXISTING:
        if parsed_valid_until is None:
            payload["validUntil"] = firestore.DELETE_FIELD
        else:
            payload["validUntil"] = parsed_valid_until

    doc_ref.set(payload, merge=True)
    await state.clear()

    action = "Updated" if existed else "Created"
    logger.info(
        "promocode saved code=%s discount=%s max_uses=%s valid_until=%s existed=%s",
        code,
        discount_fraction,
        None if max_uses is KEEP_EXISTING else max_uses,
        None if parsed_valid_until is KEEP_EXISTING else parsed_valid_until,
        existed,
    )
    max_uses_line = "unchanged"
    if max_uses is None:
        max_uses_line = "unlimited"
    elif isinstance(max_uses, int):
        max_uses_line = str(max_uses)
    valid_until_line = "unchanged"
    if parsed_valid_until is None:
        valid_until_line = "none"
    elif isinstance(parsed_valid_until, datetime):
        valid_until_line = _format_valid_until(parsed_valid_until)
    await message.answer(
        f"{action} promo code <code>{code}</code>.\n"
        f"Discount: <b>{percent:g}%</b> (stored as <code>{discount_fraction}</code>)\n"
        f"Max uses: <b>{max_uses_line}</b>\n"
        f"Valid until: <b>{valid_until_line}</b>\n"
        f"Collection: <code>{PROMOCODES_COLLECTION}</code>",
        parse_mode="HTML",
    )


@router.message(Command("delete_promocode"))
async def cmd_delete_promocode(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return
    parts = (message.text or "").strip().split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        await message.answer(
            "Usage: <code>/delete_promocode CODE</code>",
            parse_mode="HTML",
        )
        return
    code = parts[1].strip().upper()
    db = init_firestore()
    doc_ref = db.collection(PROMOCODES_COLLECTION).document(code)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        await message.answer(f"Promo code <code>{code}</code> not found.", parse_mode="HTML")
        return
    doc_ref.delete()
    logger.info("promocode deleted code=%s", code)
    await message.answer(f"Deleted promo code <code>{code}</code>.", parse_mode="HTML")


@router.message(Command("promo_stats"))
async def cmd_promo_stats(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return
    parts = (message.text or "").strip().split(maxsplit=1)
    db = init_firestore()
    collection_ref = db.collection(PROMOCODES_COLLECTION)

    if len(parts) == 2 and parts[1].strip():
        code = parts[1].strip().upper()
        snapshot = collection_ref.document(code).get()
        if not snapshot.exists:
            await message.answer(f"Promo code <code>{code}</code> not found.", parse_mode="HTML")
            return
        data = snapshot.to_dict() or {}
        await message.answer(_format_promo_stats(code, data), parse_mode="HTML")
        return

    docs = list(collection_ref.stream())
    if not docs:
        await message.answer("No promo codes found.")
        return

    lines = [
        _format_promo_stats(doc.id, doc.to_dict() or {})
        for doc in docs
    ]
    header = "Promo usage stats:\n\n"
    chunk = header
    for line in lines:
        candidate = f"{chunk}{line}\n\n"
        if len(candidate) > 3500:
            await message.answer(chunk.rstrip(), parse_mode="HTML")
            chunk = f"{line}\n\n"
        else:
            chunk = candidate
    if chunk.strip():
        await message.answer(chunk.rstrip(), parse_mode="HTML")
