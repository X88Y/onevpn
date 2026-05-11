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
    
    # We'll use batching if there are many users, but for now let's just iterate.
    # Note: firebase-admin Python SDK is synchronous for Firestore/Messaging.
    # We wrap it in a thread if needed, or just let it run if it's not too many.
    
    docs = users_ref.stream()
    tokens = []
    
    for doc in docs:
        user_data = doc.to_dict()
        devices = user_data.get("devices", [])
        for device in devices:
            token = device.get("sendnotifyToken")
            if token:
                tokens.append(token)
                
    if not tokens:
        return 0
        
    # FCM allows sending up to 500 tokens in one multicast message
    sent_total = 0
    for i in range(0, len(tokens), 500):
        batch = tokens[i:i + 500]
        multicast_message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title="MVM VPN",
                body=text,
            ),
            tokens=batch,
        )
        response = messaging.send_multicast(multicast_message)
        sent_total += response.success_count
        
        # Log failures if any
        if response.failure_count > 0:
            logger.warning("FCM: %d failures in batch", response.failure_count)
            
    return sent_total
