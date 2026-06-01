"""Periodically checks for expired / expiring subscriptions and notifies users via Telegram/VK."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

import aiohttp
import httpx
from firebase_admin import firestore

from mvm_bot.config import bot_token, vk_bot_tokens, yoomoney_receiver, yoomoney_secret, yoomoney_recurring_enabled
from mvm_bot.firebase_client import init_firebase
from mvm_bot.yoomoney import build_label
from mvm_bot.constants import SUBSCRIPTION_PLANS, BOT_DIR
from pathlib import Path

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


async def attempt_autocharge(
    user_id: str,
    plan_key: str,
    payment_method_id: str,
    provider: str,
) -> bool:
    """Attempt to charge a saved payment method using YooKassa REST API."""
    receiver = yoomoney_receiver()
    secret = yoomoney_secret()
    if not receiver or not secret:
        logger.error("Autocharge failed: receiver or secret not configured")
        return False

    plan = SUBSCRIPTION_PLANS.get(plan_key)
    if not plan:
        logger.error(f"Autocharge failed: plan {plan_key} not found")
        return False

    amount = plan["rub"]
    label = build_label(provider, user_id, plan_key)

    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "capture": True,
        "payment_method_id": payment_method_id,
        "description": f"Автопродление подписки MVMVpn ({plan['label']})",
        "metadata": {
            "label": label
        }
    }

    headers = {
        "Idempotence-Key": label,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.yookassa.ru/v3/payments",
                json=payload,
                headers=headers,
                auth=(receiver, secret),
                timeout=15.0
            )
            if response.status_code in (200, 201):
                data = response.json()
                status = data.get("status")
                if status == "succeeded":
                    logger.info(f"Autocharge succeeded for user {user_id} via label {label}")
                    return True
                else:
                    logger.warning(f"Autocharge returned status {status} for user {user_id}")
                    return False
            else:
                logger.error(f"Autocharge API request failed: {response.status_code} {response.text}")
                return False
    except Exception:
        logger.exception(f"Autocharge error for user {user_id}")
        return False


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

            # Send only once per subscription expiry: compare stored expiry ts
            # with the current subscriptionEndsAt so a renewed-then-expired user
            # gets notified again, but a still-expired user is never spammed.
            current_end_ms = _timestamp_ms(current_end)
            notified_for_ms = _timestamp_ms(user_data.get("expiryNotifiedForDateMs"))
            if notified_for_ms is not None and current_end_ms is not None and notified_for_ms >= current_end_ms:
                continue

            tg_id = _extract_provider_id(user_data.get("externalTg"))
            vk_id = _extract_provider_id(user_data.get("externalVk"))

            if not tg_id and not vk_id:
                continue

            payment_method_id = user_data.get("yookassaPaymentMethodId")
            if payment_method_id and yoomoney_recurring_enabled():
                # Try auto-charging
                last_attempt = user_data.get("yookassaLastChargeAttemptAt")
                should_charge = True
                if last_attempt:
                    if hasattr(last_attempt, "timestamp"):
                        last_attempt_dt = last_attempt
                    else:
                        try:
                            last_attempt_dt = datetime.fromisoformat(str(last_attempt))
                        except Exception:
                            last_attempt_dt = None
                    if last_attempt_dt and (datetime.now(timezone.utc) - last_attempt_dt < timedelta(hours=24)):
                        should_charge = False

                if should_charge:
                    provider = "tg" if tg_id else "vk"
                    uid = tg_id if tg_id else vk_id
                    plan_key = user_data.get("yookassaPlanKey") or "plan_30"

                    # Update last attempt time in Firestore
                    ref = snap.reference
                    await asyncio.to_thread(
                        lambda r=ref, ts=datetime.now(timezone.utc): r.update({"yookassaLastChargeAttemptAt": ts})
                    )

                    success = await attempt_autocharge(
                        user_id=uid,
                        plan_key=plan_key,
                        payment_method_id=payment_method_id,
                        provider=provider,
                    )
                    if success:
                        # Auto-charge succeeded. The webhook will handle extending subscription.
                        continue
                    else:
                        # Auto-charge failed. Notify user.
                        fail_text = (
                            "⚠️ Автоматическое продление вашей подписки не удалось (например, недостаточно средств на карте).\n\n"
                            "Пожалуйста, продлите подписку вручную в личном кабинете."
                        )
                        if tg_id:
                            await _notify_telegram(tg_id, fail_text)
                        if vk_id:
                            await _notify_vk(vk_id, fail_text)
                        continue
                else:
                    # Already tried recently, skip
                    continue

            text = (
                "Ваша подписка закончилась❗️\n\n"
                "Что бы продолжить использовать VPN, оформите подписку."
            )

            if tg_id:
                await _notify_telegram(tg_id, text)
            if vk_id:
                await _notify_vk(vk_id, text)

            ref = snap.reference
            current_end_ms = _timestamp_ms(current_end)
            await asyncio.to_thread(
                lambda r=ref, ts=current_end_ms: r.update({"expiryNotifiedForDateMs": ts})
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

    notified_count = 0
    for snap in snaps:
        try:
            user_data = snap.to_dict() or {}

            current_end = user_data.get("subscriptionEndsAt")
            if current_end is None:
                continue

            current_end_ms = _timestamp_ms(current_end)
            notified_for_ms = _timestamp_ms(user_data.get("preExpiryNotifiedAtMs"))
            if notified_for_ms is not None and current_end_ms is not None and notified_for_ms >= current_end_ms:
                continue

            tg_id = _extract_provider_id(user_data.get("externalTg"))
            vk_id = _extract_provider_id(user_data.get("externalVk"))

            if not tg_id and not vk_id:
                continue

            payment_method_id = user_data.get("yookassaPaymentMethodId")
            if payment_method_id and yoomoney_recurring_enabled():
                # Try auto-charging
                last_attempt = user_data.get("yookassaLastChargeAttemptAt")
                should_charge = True
                if last_attempt:
                    if hasattr(last_attempt, "timestamp"):
                        last_attempt_dt = last_attempt
                    else:
                        try:
                            last_attempt_dt = datetime.fromisoformat(str(last_attempt))
                        except Exception:
                            last_attempt_dt = None
                    if last_attempt_dt and (datetime.now(timezone.utc) - last_attempt_dt < timedelta(hours=24)):
                        should_charge = False

                if should_charge:
                    provider = "tg" if tg_id else "vk"
                    uid = tg_id if tg_id else vk_id
                    plan_key = user_data.get("yookassaPlanKey") or "plan_30"

                    # Update last attempt time in Firestore
                    ref = snap.reference
                    await asyncio.to_thread(
                        lambda r=ref, ts=datetime.now(timezone.utc): r.update({"yookassaLastChargeAttemptAt": ts})
                    )

                    success = await attempt_autocharge(
                        user_id=uid,
                        plan_key=plan_key,
                        payment_method_id=payment_method_id,
                        provider=provider,
                    )
                    if success:
                        # Auto-charge succeeded. Webhook will extend subscription.
                        continue
                    else:
                        # Auto-charge failed. Notify user.
                        fail_text = (
                            "⚠️ Автоматическое продление вашей подписки не удалось (например, недостаточно средств на карте).\n\n"
                            "Пожалуйста, продлите подписку вручную в личном кабинете."
                        )
                        if tg_id:
                            await _notify_telegram(tg_id, fail_text)
                        if vk_id:
                            await _notify_vk(vk_id, fail_text)
                        continue
                else:
                    # Already tried recently, skip
                    continue

            end_str = ""
            if hasattr(current_end, "strftime"):
                end_str = current_end.strftime("%d.%m.%Y")
            else:
                end_str = str(current_end)

            text = (
                f"⏳ Ваша подписка скоро закончится {end_str}\n\n"
                "Что бы оставаться на связи и не потерять доступ в интернет, продлите подписку."
            )

            if tg_id:
                await _notify_telegram(tg_id, text)
            if vk_id:
                await _notify_vk(vk_id, text)

            ref = snap.reference
            current_end_ms = _timestamp_ms(current_end)
            await asyncio.to_thread(
                lambda r=ref, ts=current_end_ms: r.update({"preExpiryNotifiedAtMs": ts})
            )
            notified_count += 1
        except Exception:
            logger.exception("failed to notify expiring-soon user %s", snap.id)

    if notified_count:
        logger.info("sent pre-expiry notifications to %s users", notified_count)


async def _notify_telegram_photo(user_id: str, photo_path: Path, caption: str, reply_markup: dict = None) -> bool:
    from mvm_bot.firebase_client import get_tg_cached_attachment, set_tg_cached_attachment
    token = bot_token()
    
    cached_file_id = await get_tg_cached_attachment(token, [photo_path.name])
    
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        if cached_file_id:
            data = aiohttp.FormData()
            data.add_field('chat_id', str(user_id))
            data.add_field('caption', caption)
            data.add_field('parse_mode', 'HTML')
            data.add_field('photo', cached_file_id)
            if reply_markup:
                import json
                data.add_field('reply_markup', json.dumps(reply_markup))
                
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        return True
                    else:
                        body = await resp.text()
                        logger.warning("telegram notify photo with cached file_id failed, will try re-upload: %s %s", resp.status, body)
        
        data = aiohttp.FormData()
        data.add_field('chat_id', str(user_id))
        data.add_field('caption', caption)
        data.add_field('parse_mode', 'HTML')
        if reply_markup:
            import json
            data.add_field('reply_markup', json.dumps(reply_markup))
            
        with open(photo_path, 'rb') as f:
            data.add_field('photo', f, filename=photo_path.name)
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.warning("telegram notify photo upload failed: %s %s", resp.status, body)
                        return False
                    res_json = await resp.json()
                    file_id = res_json.get("result", {}).get("photo", [{}])[-1].get("file_id")
                    if file_id:
                        await set_tg_cached_attachment(token, [photo_path.name], file_id)
                    return True
    except Exception:
        logger.exception("telegram notify photo error for user %s", user_id)
        return False


async def _notify_vk_photo(user_id: str, photo_path: Path, caption: str, keyboard: str = None) -> bool:
    from mvm_bot.firebase_client import get_vk_cached_attachment, set_vk_cached_attachment
    tokens = vk_bot_tokens()
    if not tokens:
        logger.warning("vk notify photo: no tokens configured")
        return False
        
    for token in tokens:
        cached_attachment = await get_vk_cached_attachment(token, [photo_path.name])
        
        try:
            if cached_attachment:
                params = {
                    "user_id": user_id,
                    "message": caption,
                    "attachment": cached_attachment,
                    "random_id": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
                    "access_token": token,
                    "v": "5.231",
                }
                if keyboard:
                    params["keyboard"] = keyboard
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.vk.com/method/messages.send", params=params
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if not data.get("error"):
                                return True
                            else:
                                logger.warning("vk notify photo with cached attachment failed: %s", data["error"])
            
            from vkbottle import API
            from vkbottle.tools import PhotoMessageUploader
            api = API(token)
            uploader = PhotoMessageUploader(api)
            attachment = await uploader.upload(file_source=str(photo_path))
            
            await set_vk_cached_attachment(token, [photo_path.name], attachment)
            
            params = {
                "user_id": user_id,
                "message": caption,
                "attachment": attachment,
                "random_id": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
                "access_token": token,
                "v": "5.231",
            }
            if keyboard:
                params["keyboard"] = keyboard
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.vk.com/method/messages.send", params=params
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if not data.get("error"):
                            return True
        except Exception:
            logger.exception("vk notify photo error for user %s (token=%s...)", user_id, token[:8])
            
    logger.warning("vk notify photo: all tokens failed for user %s", user_id)
    return False


async def check_and_send_trial_retention_messages() -> None:
    db = init_firebase()
    trial_img = BOT_DIR / "assets" / "trial.jpg"
    start_img = BOT_DIR / "assets" / "start.jpg"
    
    start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    snaps = await asyncio.to_thread(
        lambda: list(
            db.collection(USERS_COLLECTION)
            .where("trialActivatedAt", ">=", start_date)
            .stream()
        )
    )
    if not snaps:
        return
        
    now = datetime.now(timezone.utc)
    
    for snap in snaps:
        try:
            user_data = snap.to_dict() or {}
            
            ends_at = user_data.get("subscriptionEndsAt")
            if not ends_at:
                continue
            if hasattr(ends_at, "timestamp"):
                ends_at_dt = ends_at
            else:
                try:
                    ends_at_dt = datetime.fromisoformat(str(ends_at))
                except Exception:
                    continue
            if ends_at_dt.tzinfo is None:
                ends_at_dt = ends_at_dt.replace(tzinfo=timezone.utc)
                
            if ends_at_dt <= now:
                continue
                
            trial_act = user_data.get("trialActivatedAt")
            if not trial_act:
                continue
            if hasattr(trial_act, "timestamp"):
                trial_act_dt = trial_act
            else:
                try:
                    trial_act_dt = datetime.fromisoformat(str(trial_act))
                except Exception:
                    continue
            if trial_act_dt.tzinfo is None:
                trial_act_dt = trial_act_dt.replace(tzinfo=timezone.utc)
                
            elapsed = now - trial_act_dt
            
            from mvm_bot.user_service.helpers import _remnawave_username
            from mvm_bot.remnawave_client import get_user_by_username, RemnawaveError

            username = _remnawave_username(snap.id)
            total_traffic = 0
            try:
                rw_user = await get_user_by_username(username)
                if rw_user:
                    total_traffic = rw_user.get("userTraffic", {}).get("usedTrafficBytes", 0)
            except RemnawaveError:
                logger.warning("Remnawave client is not configured, skipping trial retention check for user %s", snap.id)
                continue
            except Exception:
                logger.exception("Failed to get Remnawave user traffic for %s", snap.id)

            if total_traffic >= 100 * 1024 * 1024:
                continue
                
            tg_id = _extract_provider_id(user_data.get("externalTg"))
            vk_id = _extract_provider_id(user_data.get("externalVk"))
            if not tg_id and not vk_id:
                continue
                
            ref = snap.reference
            
            if elapsed >= timedelta(hours=3) and not user_data.get("trialFollowUp1Sent"):
                caption = (
                    "Видим, что Вы активировали пробный период, но не пользуетесь VPN🤔\n\n"
                    "Чтобы интернет снова заработал без ограничений, осталось выполнить 2 простых шага.\n\n"
                    "Посмотрите видео инструкцию, в ней подробно рассказываем, как подключиться🫶 — "
                    "https://vk.ru/clip-223445666_456239017"
                )
                success = False
                if tg_id:
                    success = await _notify_telegram_photo(tg_id, trial_img, caption)
                if vk_id:
                    success_vk = await _notify_vk_photo(vk_id, trial_img, caption)
                    success = success or success_vk
                    
                if success:
                    await asyncio.to_thread(ref.update, {"trialFollowUp1Sent": True})
                    logger.info("Sent trial follow-up 1 to user %s", snap.id)
                    
            if elapsed >= timedelta(days=1) and not user_data.get("trialFollowUp2Sent"):
                caption = (
                    "Ну что, получилось разобраться?\n\n"
                    "Если возникли неполадки в процессе подключения или по каким то причинам VPN не работает, "
                    "наша команда поддержки с удовольствием готова помочь👇\n\n"
                    "VK - https://vk.ru/mvmhelp\n"
                    "TG - https://t.me/MVM_Support"
                )
                success = False
                if tg_id:
                    success = await _notify_telegram_photo(tg_id, start_img, caption)
                if vk_id:
                    success_vk = await _notify_vk_photo(vk_id, start_img, caption)
                    success = success or success_vk
                    
                if success:
                    await asyncio.to_thread(ref.update, {"trialFollowUp2Sent": True})
                    logger.info("Sent trial follow-up 2 to user %s", snap.id)
        except Exception:
            logger.exception("Failed to process trial retention for user %s", snap.id)


def build_vk_survey_keyboard() -> str:
    import json
    return json.dumps({
        "inline": True,
        "buttons": [
            [{"action": {"type": "callback", "label": "Плохо работало", "payload": json.dumps({"c": "survey", "r": "bad"})}}],
            [{"action": {"type": "callback", "label": "Дорого", "payload": json.dumps({"c": "survey", "r": "expensive"})}}],
            [{"action": {"type": "callback", "label": "Пользуюсь другим VPN", "payload": json.dumps({"c": "survey", "r": "other_vpn"})}}],
            [{"action": {"type": "callback", "label": "Другое", "payload": json.dumps({"c": "survey", "r": "other"})}}],
            [{"action": {"type": "callback", "label": "Оформлю подписку чуть позже🫶", "payload": json.dumps({"c": "survey", "r": "later"})}}],
        ]
    })


async def check_and_send_retention_surveys() -> None:
    db = init_firebase()
    now = datetime.now(timezone.utc)
    one_day_ago = now - timedelta(days=1)
    seven_days_ago = now - timedelta(days=7)
    
    snaps = await asyncio.to_thread(
        lambda: list(
            db.collection(USERS_COLLECTION)
            .where("subscriptionEndsAt", "<", one_day_ago)
            .where("subscriptionEndsAt", ">", seven_days_ago)
            .stream()
        )
    )
    if not snaps:
        return
        
    for snap in snaps:
        try:
            user_data = snap.to_dict() or {}
            
            if user_data.get("expirySurveySent"):
                continue
                
            tg_id = _extract_provider_id(user_data.get("externalTg"))
            vk_id = _extract_provider_id(user_data.get("externalVk"))
            if not tg_id and not vk_id:
                continue
                
            text = (
                "Ваша подписка закончилась и вы её не продлили🤔\n\n"
                "Помогите нам стать лучше. Ответьте на пару вопросов👇\n\n"
                "По какой причине вы не стали оформлять подписку?"
            )
            
            ref = snap.reference
            success = False
            
            if tg_id:
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "Плохо работало", "callback_data": "survey:bad"}],
                        [{"text": "Дорого", "callback_data": "survey:expensive"}],
                        [{"text": "Пользуюсь другим VPN", "callback_data": "survey:other_vpn"}],
                        [{"text": "Другое", "callback_data": "survey:other"}],
                        [{"text": "Оформлю подписку чуть позже🫶", "callback_data": "survey:later"}],
                    ]
                }
                token = bot_token()
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                import json
                payload = {
                    "chat_id": tg_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": keyboard
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload) as resp:
                        if resp.status == 200:
                            success = True
                            
            if vk_id:
                vk_kb = build_vk_survey_keyboard()
                tokens = vk_bot_tokens()
                for token in tokens:
                    params = {
                        "user_id": vk_id,
                        "message": text,
                        "random_id": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
                        "keyboard": vk_kb,
                        "access_token": token,
                        "v": "5.231",
                    }
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            "https://api.vk.com/method/messages.send", params=params
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if not data.get("error"):
                                    success = True
                                    break
                                    
            if success:
                await asyncio.to_thread(ref.update, {"expirySurveySent": True})
                logger.info("Sent expiry retention survey to user %s", snap.id)
        except Exception:
            logger.exception("Failed to process retention survey for user %s", snap.id)


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

        try:
            await check_and_send_trial_retention_messages()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("trial retention notifier iteration failed")

        try:
            await check_and_send_retention_surveys()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("retention survey notifier iteration failed")

        await asyncio.sleep(interval)
