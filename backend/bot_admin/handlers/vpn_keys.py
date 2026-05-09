import logging
from typing import Any, Dict, Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from firebase_admin import firestore

from bot_admin.config import admin_telegram_ids
from bot_admin.constants import VPN_KEYS_COLLECTION
from bot_admin.firebase_client import init_firestore

logger = logging.getLogger(__name__)

router = Router(name="vpn_keys")


class AddVpnKey(StatesGroup):
    doc_id = State()
    key_value = State()
    label = State()


def _is_admin(user_id: Optional[int]) -> bool:
    if user_id is None:
        return False
    return user_id in admin_telegram_ids()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return
    await message.answer(
        "Admin bot.\n\n"
        "Server pool:\n"
        "  /add_server — add a new VPN server (auto-installs 3x-ui)\n"
        "  /list_servers — list servers + status (paginated)\n"
        "  /list_server — alias for /list_servers\n"
        "  /disable_server <id>, /enable_server <id>\n\n"
        f"Legacy: /add_vpn_key still appends to `{VPN_KEYS_COLLECTION}` but is "
        "no longer read by Cloud Functions."
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return
    await state.clear()
    await message.answer("Cancelled.")


@router.message(Command("add_vpn_key"))
async def cmd_add_vpn_key(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return
    await state.set_state(AddVpnKey.doc_id)
    await message.answer(
        "Step 1/3: Send document ID for the new record, or send `auto` for a random ID."
    )


@router.message(AddVpnKey.doc_id, F.text)
async def add_step_doc_id(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await state.clear()
        await message.answer("Access denied.")
        return
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Send a non-empty document ID or `auto`.")
        return
    doc_id = None if raw.lower() == "auto" else raw
    await state.update_data(doc_id=doc_id)
    await state.set_state(AddVpnKey.key_value)
    await message.answer(
        "Step 2/3: Send the VPN key string (one message; newlines are allowed)."
    )


@router.message(AddVpnKey.key_value, F.text)
async def add_step_key_value(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await state.clear()
        await message.answer("Access denied.")
        return
    key_value = message.text or ""
    if not key_value.strip():
        await message.answer("Key cannot be empty.")
        return
    await state.update_data(key_value=key_value)
    await state.set_state(AddVpnKey.label)
    await message.answer(
        "Step 3/3: Send an optional label, or /skip to store without a label."
    )


@router.message(AddVpnKey.label, Command("skip"))
async def add_step_label_skip(message: Message, state: FSMContext) -> None:
    await _finalize_vpn_key(message, state, label=None)


@router.message(AddVpnKey.label, F.text)
async def add_step_label(message: Message, state: FSMContext) -> None:
    label = (message.text or "").strip()
    await _finalize_vpn_key(message, state, label=label or None)


async def _finalize_vpn_key(message: Message, state: FSMContext, label: Optional[str]) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await state.clear()
        await message.answer("Access denied.")
        return
    data = await state.get_data()
    doc_id: Optional[str] = data.get("doc_id")
    key_value: Optional[str] = data.get("key_value")
    if not key_value:
        await state.clear()
        await message.answer("Session expired. Run /add_vpn_key again.")
        return

    payload: Dict[str, Any] = {
        "key": key_value,
        "createdAt": firestore.SERVER_TIMESTAMP,
    }
    if label:
        payload["label"] = label

    db = init_firestore()
    col = db.collection(VPN_KEYS_COLLECTION)
    if doc_id:
        ref = col.document(doc_id)
        ref.set(payload)
        final_id = doc_id
    else:
        _, ref = col.add(payload)
        final_id = ref.id

    await state.clear()
    logger.info("vpn_keys document written id=%s", final_id)
    await message.answer(f"Saved to `{VPN_KEYS_COLLECTION}/{final_id}`.")
