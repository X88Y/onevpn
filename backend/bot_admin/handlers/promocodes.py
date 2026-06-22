import logging
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


class CreatePromocode(StatesGroup):
    code = State()
    discount_percent = State()


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


@router.message(Command("create_promocode"))
async def cmd_create_promocode(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return
    await state.clear()
    await state.set_state(CreatePromocode.code)
    await message.answer(
        "Step 1/2: send the promo code value.\n"
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
        "Step 2/2: send discount percent (1..100).\n"
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

    data = await state.get_data()
    code = str(data.get("promocode") or "").strip().upper()
    if not code:
        await state.clear()
        await message.answer("Session expired. Run /create_promocode again.")
        return

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
        payload["createdAt"] = firestore.SERVER_TIMESTAMP

    doc_ref.set(payload, merge=True)
    await state.clear()

    action = "Updated" if existed else "Created"
    logger.info("promocode saved code=%s discount=%s existed=%s", code, discount_fraction, existed)
    await message.answer(
        f"{action} promo code <code>{code}</code>.\n"
        f"Discount: <b>{percent:g}%</b> (stored as <code>{discount_fraction}</code>)\n"
        f"Collection: <code>{PROMOCODES_COLLECTION}</code>",
        parse_mode="HTML",
    )
