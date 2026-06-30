import asyncio
import hashlib
import logging
from typing import Optional, Tuple

import httpx
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from firebase_admin import firestore

from bot_admin.config import admin_telegram_ids
from bot_admin.firebase_client import init_firestore
from bot_admin.handlers.group_statistics import split_telegram_messages

logger = logging.getLogger(__name__)
router = Router(name="vk_tokens")


class AddVkToken(StatesGroup):
    token = State()
    confirm_overwrite = State()


def _is_admin(user_id: Optional[int]) -> bool:
    if user_id is None:
        return False
    return user_id in admin_telegram_ids()


async def get_vk_group_info_from_token(token: str) -> Tuple[bool, Optional[int], str]:
    params = {
        "access_token": token,
        "v": "5.199",
        "fields": "name",
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.vk.com/method/groups.getById",
                data=params,
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as e:
        logger.exception("VK API request failed")
        return False, None, f"Network/HTTP error: {e}"

    if "error" in payload:
        error_msg = payload["error"].get("error_msg", "Unknown error")
        error_code = payload["error"].get("error_code")
        return False, None, f"VK API Error {error_code}: {error_msg}"

    raw = payload.get("response")
    if isinstance(raw, dict):
        groups = raw.get("groups", [])
    elif isinstance(raw, list):
        groups = raw
    else:
        groups = []

    if not groups or not isinstance(groups[0], dict):
        return False, None, "No group info returned by VK API."

    group = groups[0]
    returned_id = group.get("id")
    if returned_id is None:
        return False, None, "VK API returned group info without an ID."

    group_name = group.get("name") or f"Group {returned_id}"
    return True, int(returned_id), group_name


@router.message(Command("add_vk_token", "add_token"))
async def cmd_add_vk_token(message: Message, command: CommandObject, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return

    await state.clear()
    token = (command.args or "").strip()

    if not token:
        await state.set_state(AddVkToken.token)
        await message.answer(
            "Please send the VK Group Access Token.\n"
            "Or use: <code>/add_vk_token &lt;token&gt;</code>\n"
            "Send /cancel at any time to abort.",
            parse_mode="HTML",
        )
        return

    try:
        await message.delete()
    except Exception:
        pass

    status_msg = await message.answer("⏳ Verifying token with VK API...")

    ok, group_id, result = await get_vk_group_info_from_token(token)
    if not ok or group_id is None:
        await status_msg.edit_text(f"❌ Token verification failed:\n{result}")
        return

    group_name = result

    def save_to_db_direct():
        db = init_firestore()
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()

        # Enforce uniqueness
        docs_int = db.collection("vk_tokens").where("group_id", "==", group_id).get()
        docs_str = db.collection("vk_tokens").where("group_id", "==", str(group_id)).get()

        for doc in list(docs_int) + list(docs_str):
            doc.reference.delete()

        db.collection("vk_tokens").document(token_hash).set({
            "token": token,
            "group_id": group_id,
            "status": "active",
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "start_identifier": None,
        })
        return token_hash

    try:
        token_hash = await asyncio.to_thread(save_to_db_direct)
        await status_msg.edit_text(
            f"✅ Successfully saved VK token!\n"
            f"Group: <b>{group_name}</b>\n"
            f"Group ID: <code>{group_id}</code>\n"
            f"Document ID (Hash): <code>{token_hash}</code>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Failed to save token to database")
        await status_msg.edit_text(f"❌ Failed to save token to database: {e}")


@router.message(AddVkToken.token, F.text)
async def process_fsm_token(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await state.clear()
        await message.answer("Access denied.")
        return

    token = (message.text or "").strip()
    try:
        await message.delete()
    except Exception:
        pass

    if not token:
        await message.answer("Token cannot be empty. Send /cancel to abort.")
        return

    status_msg = await message.answer("⏳ Verifying token with VK API...")
    ok, group_id, result = await get_vk_group_info_from_token(token)
    if not ok or group_id is None:
        await status_msg.edit_text(f"❌ Token verification failed:\n{result}\n\nPlease send a valid token, or /cancel to abort.")
        return

    group_name = result

    # Check for uniqueness in Firestore
    db = init_firestore()
    docs_int = await asyncio.to_thread(lambda: list(db.collection("vk_tokens").where("group_id", "==", group_id).get()))
    docs_str = await asyncio.to_thread(lambda: list(db.collection("vk_tokens").where("group_id", "==", str(group_id)).get()))
    all_existing = docs_int + docs_str

    if all_existing:
        await state.update_data(token=token, group_id=group_id, group_name=group_name)
        await state.set_state(AddVkToken.confirm_overwrite)

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="Yes, Replace", callback_data="vk_overwrite_yes"),
            InlineKeyboardButton(text="Cancel", callback_data="vk_overwrite_no"),
        )

        existing_tokens_info = []
        for doc in all_existing:
            data = doc.to_dict() or {}
            t = data.get("token") or ""
            masked = f"{t[:4]}...{t[-4:]}" if len(t) > 8 else "..."
            existing_tokens_info.append(f"• Document ID: <code>{doc.id}</code> (Token: <code>{masked}</code>)")

        existing_str = "\n".join(existing_tokens_info)
        await status_msg.delete()
        await message.answer(
            f"⚠️ A token for VK group <b>{group_name}</b> (ID: <code>{group_id}</code>) already exists:\n{existing_str}\n\n"
            f"Do you want to replace it?",
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
    else:
        await status_msg.edit_text("⏳ Saving token to Firebase...")

        def save_to_db():
            token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
            db.collection("vk_tokens").document(token_hash).set({
                "token": token,
                "group_id": group_id,
                "status": "active",
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "start_identifier": None,
            })
            return token_hash

        try:
            token_hash = await asyncio.to_thread(save_to_db)
            await status_msg.edit_text(
                f"✅ Successfully saved VK token!\n"
                f"Group: <b>{group_name}</b>\n"
                f"Group ID: <code>{group_id}</code>\n"
                f"Document ID (Hash): <code>{token_hash}</code>",
                parse_mode="HTML",
            )
            await state.clear()
        except Exception as e:
            logger.exception("Failed to save token to database")
            await status_msg.edit_text(f"❌ Failed to save token to database: {e}")


@router.callback_query(AddVkToken.confirm_overwrite, F.data == "vk_overwrite_yes")
async def process_overwrite_yes(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    data = await state.get_data()
    token = data.get("token")
    group_id = data.get("group_id")
    group_name = data.get("group_name")

    if not token or group_id is None:
        await callback.message.answer("Session expired or invalid data. Operation aborted.")
        await state.clear()
        await callback.answer()
        return

    status_msg = await callback.message.answer("⏳ Saving token to Firebase...")

    def save_to_db_overwrite():
        db = init_firestore()
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()

        # Enforce uniqueness
        docs_int = db.collection("vk_tokens").where("group_id", "==", group_id).get()
        docs_str = db.collection("vk_tokens").where("group_id", "==", str(group_id)).get()

        for doc in list(docs_int) + list(docs_str):
            doc.reference.delete()

        db.collection("vk_tokens").document(token_hash).set({
            "token": token,
            "group_id": group_id,
            "status": "active",
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "start_identifier": None,
        })
        return token_hash

    try:
        token_hash = await asyncio.to_thread(save_to_db_overwrite)
        await status_msg.edit_text(
            f"✅ Successfully saved VK token!\n"
            f"Group: <b>{group_name}</b>\n"
            f"Group ID: <code>{group_id}</code>\n"
            f"Document ID (Hash): <code>{token_hash}</code>",
            parse_mode="HTML",
        )
        await state.clear()
    except Exception as e:
        logger.exception("Failed to save token to database")
        await status_msg.edit_text(f"❌ Failed to save token to database: {e}")
    await callback.answer()


@router.callback_query(AddVkToken.confirm_overwrite, F.data == "vk_overwrite_no")
async def process_overwrite_no(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.clear()
    await callback.message.answer("Operation cancelled.")
    await callback.answer()


@router.message(Command("list_vk_tokens", "list_tokens"))
async def cmd_list_vk_tokens(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return

    status_msg = await message.answer("⏳ Fetching VK tokens from Firestore...")

    def get_tokens():
        db = init_firestore()
        docs = db.collection("vk_tokens").get()
        return [doc.to_dict() | {"id": doc.id} for doc in docs]

    try:
        tokens_data = await asyncio.to_thread(get_tokens)
        if not tokens_data:
            await status_msg.edit_text("No VK tokens registered in Firestore.")
            return

        async def fetch_name(tok_data):
            token = tok_data.get("token") or ""
            group_id = tok_data.get("group_id")
            status = tok_data.get("status") or "active"
            doc_id = tok_data.get("id")

            masked = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "..."

            if not group_id:
                return f"• Doc: <code>{doc_id}</code> | Token: <code>{masked}</code> | Status: <b>{status}</b> (No group_id)"

            ok, _, name_or_err = await get_vk_group_info_from_token(token)
            if ok:
                name_str = f"<b>{name_or_err}</b>"
            else:
                name_str = f"⚠️ Verification failed ({name_or_err})"

            return (
                f"• Group ID: <code>{group_id}</code> | Name: {name_str}\n"
                f"  Doc: <code>{doc_id}</code> | Token: <code>{masked}</code> | Status: <b>{status}</b>"
            )

        tasks = [fetch_name(tok) for tok in tokens_data]
        results = await asyncio.gather(*tasks)

        response_text = "📋 <b>Registered VK Tokens:</b>\n\n" + "\n\n".join(results)

        await status_msg.delete()
        for chunk in split_telegram_messages(response_text):
            await message.answer(chunk, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to list VK tokens")
        await status_msg.edit_text(f"❌ Failed to list VK tokens: {e}")


@router.message(Command("delete_vk_token", "delete_token"))
async def cmd_delete_vk_token(message: Message, command: CommandObject) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return

    arg = (command.args or "").strip()
    if not arg:
        await message.answer(
            "Usage: <code>/delete_vk_token &lt;group_id&gt;</code>\n"
            "Example: <code>/delete_vk_token 123456</code>",
            parse_mode="HTML",
        )
        return

    if not arg.isdigit():
        await message.answer("Group ID must be a positive integer.")
        return

    group_id = int(arg)
    status_msg = await message.answer(f"⏳ Deleting tokens for Group ID {group_id}...")

    def delete_by_group_id():
        db = init_firestore()
        docs_int = db.collection("vk_tokens").where("group_id", "==", group_id).get()
        docs_str = db.collection("vk_tokens").where("group_id", "==", str(group_id)).get()

        all_docs = list(docs_int) + list(docs_str)
        if not all_docs:
            return 0

        deleted_count = 0
        for doc in all_docs:
            doc.reference.delete()
            deleted_count += 1
        return deleted_count

    try:
        count = await asyncio.to_thread(delete_by_group_id)
        if count > 0:
            await status_msg.edit_text(f"✅ Successfully deleted {count} token(s) for Group ID <code>{group_id}</code>.", parse_mode="HTML")
        else:
            await status_msg.edit_text(f"❓ No tokens found for Group ID <code>{group_id}</code>.", parse_mode="HTML")
    except Exception as e:
        logger.exception("Failed to delete VK token")
        await status_msg.edit_text(f"❌ Failed to delete VK token: {e}")
