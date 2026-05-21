"""Periodically checks for expired / expiring subscriptions and notifies users via Telegram/VK."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

import aiohttp
from firebase_admin import firestore

from mvm_bot.config import bot_token, vk_bot_tokens
from mvm_bot.firebase_client import init_firebase

logger = logging.getLogger(__name__)

USERS_COLLECTION = "users"
PRE_EXPIRY_HOURS = 24


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
    if isinstance(value, (int, float)):
        return int(value)
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


async def _notify_vk_with_token(user_id: str, text: str, token: str) -> bool:
    params = {
        "user_id": user_id,
        "message": text,
        "random_id": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
        "access_token": token,
        "v": "5.231",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.vk.com/method/messages.send", params=params
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(
                        "vk notify failed (token=%s...): %s %s",
                        token[:8],
                        resp.status,
                        body,
                    )
                    return False
                data = await resp.json()
                if data.get("error"):
                    logger.warning(
                        "vk api error (token=%s...): %s",
                        token[:8],
                        data["error"],
                    )
                    return False
                return True
    except Exception:
        logger.exception("vk notify error for user %s (token=%s...)", user_id, token[:8])
        return False


async def _notify_vk(user_id: str, text: str) -> None:
    tokens = vk_bot_tokens()
    if not tokens:
        logger.warning("vk notify: no tokens configured")
        return
    for token in tokens:
        ok = await _notify_vk_with_token(user_id, text, token)
        if ok:
            return
    logger.warning("vk notify: all tokens failed for user %s", user_id)


def _fetch_expired_users(db: firestore.Client) -> List[firestore.DocumentSnapshot]:
    now = datetime.now(timezone.utc)
    return list(
        db.collection(USERS_COLLECTION)
        .where("subscriptionEndsAt", "<", now)
        .stream()
    )


def _fetch_expiring_soon_users(db: firestore.Client) -> List[firestore.DocumentSnapshot]:
    now = datetime.now(timezone.utc)
    soon = now + timedelta(hours=PRE_EXPIRY_HOURS)
    return list(
        db.collection(USERS_COLLECTION)
        .where("subscriptionEndsAt", ">=", now)
        .where("subscriptionEndsAt", "<=", soon)
        .stream()
    )


async def check_and_notify_expired_subscriptions() -> None:
    db = init_firebase()

    snaps = await asyncio.to_thread(_fetch_expired_users, db)
    if not snaps:
        return

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_ms = int(today_start.timestamp() * 1000)

    notified_count = 0
    for snap in snaps:
        try:
            user_data = snap.to_dict() or {}

            current_end = user_data.get("subscriptionEndsAt")
            if current_end is None:
                continue

            notified_for_ms = _timestamp_ms(user_data.get("expiryNotifiedForDateMs"))
            if notified_for_ms is not None and notified_for_ms >= today_start_ms:
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

            ref = snap.reference
            notified_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            await asyncio.to_thread(
                lambda r=ref, ts=notified_at_ms: r.update({"expiryNotifiedForDateMs": ts})
            )
            notified_count += 1
        except Exception:
            logger.exception("failed to notify expired user %s", snap.id)

    if notified_count:
        logger.info("sent expiry notifications to %s users", notified_count)


async def check_and_notify_expiring_soon_subscriptions() -> None:
    db = init_firebase()

    snaps = await asyncio.to_thread(_fetch_expiring_soon_users, db)
    if not snaps:
        return

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_ms = int(today_start.timestamp() * 1000)

    notified_count = 0
    for snap in snaps:
        try:
            user_data = snap.to_dict() or {}

            current_end = user_data.get("subscriptionEndsAt")
            if current_end is None:
                continue

            notified_for_ms = _timestamp_ms(user_data.get("preExpiryNotifiedAtMs"))
            if notified_for_ms is not None and notified_for_ms >= today_start_ms:
                continue

            tg_id = _extract_provider_id(user_data.get("externalTg"))
            vk_id = _extract_provider_id(user_data.get("externalVk"))

            if not tg_id and not vk_id:
                continue

            end_str = ""
            if hasattr(current_end, "strftime"):
                end_str = current_end.strftime("%d.%m.%Y")
            else:
                end_str = str(current_end)

            text = (
                f"⏳ Ваша подписка заканчивается {end_str}.\n\n"
                "Чтобы не остаться без VPN, продлите подписку заранее."
            )

            if tg_id:
                await _notify_telegram(tg_id, text)
            if vk_id:
                await _notify_vk(vk_id, text)

            ref = snap.reference
            notified_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            await asyncio.to_thread(
                lambda r=ref, ts=notified_at_ms: r.update({"preExpiryNotifiedAtMs": ts})
            )
            notified_count += 1
        except Exception:
            logger.exception("failed to notify expiring-soon user %s", snap.id)

    if notified_count:
        logger.info("sent pre-expiry notifications to %s users", notified_count)


async def run_expiry_notifier_loop() -> None:
    interval = 3600  # 1 hour
    logger.info("expiry notifier worker started interval=%ss", interval)
    while True:
        try:
            await check_and_notify_expiring_soon_subscriptions()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("pre-expiry notifier iteration failed")

        try:
            await check_and_notify_expired_subscriptions()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("expiry notifier iteration failed")

        await asyncio.sleep(interval)
