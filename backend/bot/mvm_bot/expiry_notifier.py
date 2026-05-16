"""Periodically checks for expired subscriptions and notifies users via Telegram/VK."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

import aiohttp
from firebase_admin import firestore

from mvm_bot.config import bot_token, vk_bot_token
from mvm_bot.firebase_client import init_firebase

logger = logging.getLogger(__name__)

USERS_COLLECTION = "users"


def _extract_provider_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value)
    if s.startswith("tg:"):
        return s[3:]
    if s.startswith("vk:"):
        return s[3:]
    return s


def _timestamp_ms(value: Any) -> Optional[int]:
    if value is None:
        return None
    if hasattr(value, "timestamp"):
        return int(value.timestamp() * 1000)
    return None


async def _notify_telegram(user_id: str, text: str) -> None:
    token = bot_token()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": user_id,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning("telegram notify failed: %s %s", resp.status, body)
    except Exception:
        logger.exception("telegram notify error for user %s", user_id)


async def _notify_vk(user_id: str, text: str) -> None:
    token = vk_bot_token()
    params = {
        "user_id": user_id,
        "message": text,
        "random_id": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
        "access_token": token,
        "v": "5.131",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.vk.com/method/messages.send", params=params
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning("vk notify failed: %s %s", resp.status, body)
                    return
                data = await resp.json()
                if data.get("error"):
                    logger.warning("vk api error: %s", data["error"])
    except Exception:
        logger.exception("vk notify error for user %s", user_id)


def _fetch_expired_users(db: firestore.Client) -> List[firestore.DocumentSnapshot]:
    now = datetime.now(timezone.utc)
    return list(
        db.collection(USERS_COLLECTION)
        .where("subscriptionEndsAt", "<", now)
        .stream()
    )


async def check_and_notify_expired_subscriptions() -> None:
    db = init_firebase()

    snaps = await asyncio.to_thread(_fetch_expired_users, db)
    if not snaps:
        return

    notified_count = 0
    for snap in snaps:
        try:
            user_data = snap.to_dict() or {}

            current_end = user_data.get("subscriptionEndsAt")
            if current_end is None:
                continue

            current_end_ms = _timestamp_ms(current_end)
            if current_end_ms is None:
                continue

            notified_for_ms = _timestamp_ms(user_data.get("expiryNotifiedForDateMs"))
            if notified_for_ms == current_end_ms:
                continue

            tg_id = _extract_provider_id(user_data.get("externalTg"))
            vk_id = _extract_provider_id(user_data.get("externalVk"))

            if not tg_id and not vk_id:
                continue

            text = (
                "⌛ Ваша подписка истекла.\n\n"
                "Чтобы продолжить пользоваться VPN, оформите подписку."
            )

            if tg_id:
                await _notify_telegram(tg_id, text)
            if vk_id:
                await _notify_vk(vk_id, text)

            await asyncio.to_thread(
                lambda: snap.reference.update({"expiryNotifiedForDateMs": current_end_ms})
            )
            notified_count += 1
        except Exception:
            logger.exception("failed to notify user %s", snap.id)

    if notified_count:
        logger.info("sent expiry notifications to %s users", notified_count)


async def run_expiry_notifier_loop() -> None:
    interval = 3600  # 1 hour
    logger.info("expiry notifier worker started interval=%ss", interval)
    while True:
        try:
            await check_and_notify_expired_subscriptions()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("expiry notifier iteration failed")
        await asyncio.sleep(interval)
