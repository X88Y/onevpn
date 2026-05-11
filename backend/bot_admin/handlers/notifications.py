import logging
import asyncio
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from firebase_admin import messaging

from bot_admin.config import admin_telegram_ids
from bot_admin.constants import USERS_COLLECTION
from bot_admin.firebase_client import init_firestore

logger = logging.getLogger(__name__)
router = Router(name="notifications")


class SendMessage(StatesGroup):
    text = State()
    confirm = State()


def _is_admin(user_id: Optional[int]) -> bool:
    if user_id is None:
        return False
    return user_id in admin_telegram_ids()


@router.message(Command("send_message"))
async def cmd_send_message(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return
    await state.set_state(SendMessage.text)
    await message.answer(
        "Send the message text you want to broadcast to all mobile users.\n"
        "Send /cancel to abort."
    )


@router.message(SendMessage.text, F.text)
async def send_step_text(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await state.clear()
        await message.answer("Access denied.")
        return
    
    text = (message.text or "").strip()
    if not text:
        await message.answer("Message cannot be empty.")
        return
        
    await state.update_data(broadcast_text=text)
    await state.set_state(SendMessage.confirm)
    await message.answer(
        f"Broadcast message:\n\n\"<b>{text}</b>\"\n\n"
        "Are you sure? Type <code>yes</code> to send to all users, or /cancel to abort.",
        parse_mode="HTML"
    )


@router.message(SendMessage.confirm, F.text.lower() == "yes")
async def send_step_confirm(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await state.clear()
        await message.answer("Access denied.")
        return
        
    data = await state.get_data()
    text = data.get("broadcast_text")
    await state.clear()
    
    if not text:
        await message.answer("Session expired. Run /send_message again.")
        return
        
    status_msg = await message.answer("Starting broadcast...")
    
    try:
        sent_count = await _broadcast_notification(text)
        await status_msg.edit_text(f"✅ Broadcast complete. Sent to {sent_count} devices.")
    except Exception as e:
        logger.exception("Broadcast failed")
        await status_msg.edit_text(f"❌ Broadcast failed: {e}")


async def _broadcast_notification(text: str) -> int:
    db = init_firestore()
    users_ref = db.collection(USERS_COLLECTION)
    
    # Track which token belongs to which document ID for cleanup
    token_entries = [] # List of dicts: {"token": str, "doc_id": str}
    
    # Firestore stream is blocking, wrap it in a thread
    def get_token_entries():
        entries = []
        docs = users_ref.stream()
        for doc in docs:
            user_data = doc.to_dict()
            devices = user_data.get("devices", [])
            for device in devices:
                token = device.get("sendnotifyToken")
                if token:
                    entries.append({"token": token, "doc_id": doc.id})
        return entries

    token_entries = await asyncio.to_thread(get_token_entries)
                
    if not token_entries:
        return 0
        
    tokens = [e["token"] for e in token_entries]
    sent_total = 0
    stale_tokens = [] # List of (doc_id, token)
    
    # FCM allows sending up to 500 tokens in one multicast message
    for i in range(0, len(tokens), 500):
        batch_tokens = tokens[i:i + 500]
        batch_entries = token_entries[i:i + 500]
        
        multicast_message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title="MVM VPN",
                body=text,
            ),
            tokens=batch_tokens,
        )
        
        # messaging calls are blocking, wrap in a thread
        response = await asyncio.to_thread(messaging.send_each_for_multicast, multicast_message)
        sent_total += response.success_count
        
        # Log failures and collect stale tokens
        if response.failure_count > 0:
            logger.warning("FCM: %d failures in batch of %d", response.failure_count, len(batch_tokens))
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    token = batch_tokens[idx]
                    doc_id = batch_entries[idx]["doc_id"]
                    error = resp.exception
                    logger.warning("FCM error for doc %s: %s", doc_id, error)
                    
                    # If token is unregistered or invalid, mark for removal
                    # UnregisteredError, SenderIdMismatchError, InvalidArgumentError are usually terminal
                    if isinstance(error, (messaging.UnregisteredError, messaging.SenderIdMismatchError, messaging.InvalidArgumentError)):
                        stale_tokens.append((doc_id, token))
    
    # Clean up stale tokens if any found
    if stale_tokens:
        await asyncio.to_thread(_remove_stale_tokens, db, stale_tokens)
            
    return sent_total


def _remove_stale_tokens(db, stale_tokens: list):
    """Removes stale FCM tokens from user documents in Firestore."""
    from collections import defaultdict
    grouped = defaultdict(list)
    for doc_id, token in stale_tokens:
        grouped[doc_id].append(token)
        
    for doc_id, tokens in grouped.items():
        try:
            doc_ref = db.collection(USERS_COLLECTION).document(doc_id)
            doc = doc_ref.get()
            if doc.exists:
                user_data = doc.to_dict()
                devices = user_data.get("devices", [])
                new_devices = [d for d in devices if d.get("sendnotifyToken") not in tokens]
                if len(new_devices) != len(devices):
                    doc_ref.update({"devices": new_devices})
                    logger.info("Removed %d stale tokens from user document %s", len(devices) - len(new_devices), doc_id)
        except Exception as e:
            logger.error("Failed to remove stale tokens for user %s: %s", doc_id, e)
