"""Periodically checks for trial retention and handles incoming expiration webhook events."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import urlparse, urlunparse

import aiohttp
from firebase_admin import firestore

from mvm_bot.config import bot_token
from mvm_bot.constants import BOT_DIR
from mvm_bot.expiry_autocharge import maybe_handle_autocharge
from mvm_bot.expiry_outbound import (
    build_vk_survey_keyboard as _build_vk_survey_keyboard,
    notify_telegram_photo,
    notify_vk_photo,
)
from mvm_bot.firebase_client import init_firebase, get_vk_tokens_for_user
from mvm_bot.remnawave_client import RemnawaveError, get_user_by_username
from mvm_bot.user_service.helpers import _remnawave_username
from remnawave_webhook_server.notifications import notify_tg_user, notify_vk_user

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
    if isinstance(value, (int, float)):
        return int(value)
    if hasattr(value, "timestamp"):
        return int(value.timestamp() * 1000)
    return None


async def _notify_telegram(user_id: str, text: str) -> None:
    await notify_tg_user(user_id, text)


async def _notify_vk(user_id: str, text: str) -> None:
    await notify_vk_user(user_id, text)


class DocumentSnapWrapper:
    def __init__(self, ref: firestore.DocumentReference):
        self.reference = ref


async def _notify_telegram_photo(
    user_id: str,
    photo_path: Path,
    caption: str,
    reply_markup: dict | None = None,
) -> bool:
    return await notify_telegram_photo(
        user_id,
        photo_path,
        caption,
        logger=logger,
        reply_markup=reply_markup,
    )


async def _notify_vk_photo(
    user_id: str,
    photo_path: Path,
    caption: str,
    keyboard: str | None = None,
) -> bool:
    return await notify_vk_photo(
        user_id,
        photo_path,
        caption,
        logger=logger,
        keyboard=keyboard,
    )


def _replace_domain(url: str, new_domain: str) -> str:
    try:
        parsed = urlparse(url)
        new_parsed = parsed._replace(netloc=new_domain)
        return urlunparse(new_parsed)
    except Exception:
        return url


async def handle_user_not_connected(db: firestore.Client, user_data: dict, meta: dict) -> None:
    try:
        doc_id = user_data.get("_doc_id")
        if not doc_id:
            return

        trial_act = user_data.get("trialActivatedAt")
        if not trial_act:
            logger.info("Ignoring user.not_connected for %s: not a trial user (trialActivatedAt missing)", doc_id)
            return

        if hasattr(trial_act, "timestamp"):
            trial_act_dt = trial_act
        else:
            try:
                trial_act_dt = datetime.fromisoformat(str(trial_act))
            except Exception:
                logger.info("Ignoring user.not_connected for %s: trialActivatedAt format is invalid", doc_id)
                return

        if trial_act_dt.tzinfo is None:
            trial_act_dt = trial_act_dt.replace(tzinfo=timezone.utc)

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        if trial_act_dt < start_date:
            logger.info("Ignoring user.not_connected for %s: trial activated before start date 2025-01-01", doc_id)
            return

        ends_at = user_data.get("subscriptionEndsAt")
        if not ends_at:
            logger.info("Ignoring user.not_connected for %s: subscriptionEndsAt missing", doc_id)
            return

        if hasattr(ends_at, "timestamp"):
            ends_at_dt = ends_at
        else:
            try:
                ends_at_dt = datetime.fromisoformat(str(ends_at))
            except Exception:
                logger.info("Ignoring user.not_connected for %s: subscriptionEndsAt format is invalid", doc_id)
                return

        if ends_at_dt.tzinfo is None:
            ends_at_dt = ends_at_dt.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        if ends_at_dt <= now:
            logger.info("Ignoring user.not_connected for %s: subscription already ended", doc_id)
            return

        username = _remnawave_username(doc_id)
        total_traffic = 0
        try:
            rw_user = await get_user_by_username(username)
            if rw_user:
                total_traffic = rw_user.get("userTraffic", {}).get("usedTrafficBytes", 0)
        except RemnawaveError:
            logger.warning("Remnawave client is not configured, skipping trial retention check for user %s", doc_id)
            return
        except Exception:
            logger.exception("Failed to get Remnawave user traffic for %s", doc_id)
            return

        if total_traffic >= 100 * 1024 * 1024:
            logger.info("Ignoring user.not_connected for %s: user traffic is >= 100MB (%d bytes)", doc_id, total_traffic)
            return

        hours_offline = meta.get("notConnectedAfterHours")
        if hours_offline is None:
            logger.warning("user.not_connected event missing notConnectedAfterHours in meta for user %s", doc_id)
            return

        try:
            hours_offline = int(hours_offline)
        except (ValueError, TypeError):
            logger.warning("Invalid notConnectedAfterHours value: %s for user %s", hours_offline, doc_id)
            return

        tg_id = _extract_provider_id(user_data.get("externalTg"))
        vk_id = _extract_provider_id(user_data.get("externalVk"))
        if not tg_id and not vk_id:
            logger.info("Ignoring user.not_connected for %s: no TG/VK provider ID", doc_id)
            return

        trial_img = BOT_DIR / "assets" / "trial.jpg"
        start_img = BOT_DIR / "assets" / "start.jpg"
        ref = db.collection("users").document(doc_id)

        if hours_offline == 3:
            if user_data.get("trialFollowUp1Sent"):
                logger.info("Trial follow-up 1 already sent to user %s", doc_id)
                return

            caption = (
                "Видим, что Вы активировали пробный период, но не пользуетесь VPN🤔\n\n"
                "Чтобы интернет снова заработал без ограничений, осталось выполнить 2 простых шага.\n\n"
                "Посмотрите видео инструкцию, в ней подробно рассказываем, как подключиться🫶 — "
                "https://vk.ru/clip-223445666_456239027\n\n"
                "К белым спискам — https://vk.ru/clip-223445666_456239020"
            )

            tg_reply_markup = None
            vk_keyboard = None
            sub_url = user_data.get("remnawaveSubscriptionUrl")
            if sub_url:
                tg_reply_markup = {
                    "inline_keyboard": [
                        [{"text": "🔗 Подключить", "url": sub_url}],
                        [{"text": "Резерв №1", "url": _replace_domain(sub_url, "jl1x2z77a9.cdn.twcstorage.ru")}],
                        [{"text": "Резерв №2", "url": _replace_domain(sub_url, "gpy4me9ehp.cdn.twcstorage.ru")}],
                        [{"text": "Резерв №3", "url": _replace_domain(sub_url, "hd6458sp7z.cdn.twcstorage.ru")}],
                    ]
                }
                vk_keyboard = json.dumps({
                    "inline": True,
                    "buttons": [
                        [{"action": {"type": "open_link", "label": "🔗 Подключить", "link": sub_url}}],
                        [{"action": {"type": "open_link", "label": "Резерв №1", "link": _replace_domain(sub_url, "jl1x2z77a9.cdn.twcstorage.ru")}}],
                        [{"action": {"type": "open_link", "label": "Резерв №2", "link": _replace_domain(sub_url, "gpy4me9ehp.cdn.twcstorage.ru")}}],
                        [{"action": {"type": "open_link", "label": "Резерв №3", "link": _replace_domain(sub_url, "hd6458sp7z.cdn.twcstorage.ru")}}],
                    ]
                })

            success = False
            if tg_id:
                success = await _notify_telegram_photo(tg_id, trial_img, caption, reply_markup=tg_reply_markup)
            if vk_id:
                success_vk = await _notify_vk_photo(vk_id, trial_img, caption, keyboard=vk_keyboard)
                success = success or success_vk

            if success:
                await asyncio.to_thread(ref.update, {"trialFollowUp1Sent": True})
                logger.info("Sent trial follow-up 1 to user %s via user.not_connected (3h)", doc_id)

        elif hours_offline == 24:
            if user_data.get("trialFollowUp2Sent"):
                logger.info("Trial follow-up 2 already sent to user %s", doc_id)
                return

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
                logger.info("Sent trial follow-up 2 to user %s via user.not_connected (24h)", doc_id)
        else:
            logger.info("Ignored user.not_connected for %s with unsupported hours threshold: %d", doc_id, hours_offline)

    except Exception:
        logger.exception("Failed to process trial retention for user %s", user_data.get("_doc_id"))


def build_vk_survey_keyboard() -> str:
    return _build_vk_survey_keyboard()


async def handle_user_expired(db: firestore.Client, user_data: dict) -> None:
    try:
        current_end = user_data.get("subscriptionEndsAt")
        if current_end is None:
            return

        current_end_ms = _timestamp_ms(current_end)
        notified_for_ms = _timestamp_ms(user_data.get("expiryNotifiedForDateMs"))
        if notified_for_ms is not None and current_end_ms is not None and notified_for_ms >= current_end_ms:
            return

        tg_id = _extract_provider_id(user_data.get("externalTg"))
        vk_id = _extract_provider_id(user_data.get("externalVk"))

        if not tg_id and not vk_id:
            return

        doc_id = user_data.get("_doc_id")
        ref = db.collection("users").document(doc_id)
        snap = DocumentSnapWrapper(ref)

        if await maybe_handle_autocharge(
            snap=snap,
            user_data=user_data,
            tg_id=tg_id,
            vk_id=vk_id,
            notify_telegram=_notify_telegram,
            notify_vk=_notify_vk,
            logger=logger,
        ):
            return

        text = (
            "Ваша подписка закончилась❗️\n\n"
            "Что бы продолжить использовать VPN, оформите подписку."
        )

        if tg_id:
            await _notify_telegram(tg_id, text)
        if vk_id:
            await _notify_vk(vk_id, text)

        logger.info("sent expiry notification to user %s", doc_id)
    except Exception:
        logger.exception("failed to handle user expired event for %s", user_data.get("_doc_id"))


async def handle_user_expiring_soon(db: firestore.Client, user_data: dict, offset: Optional[int]) -> None:
    try:
        doc_id = user_data.get("_doc_id")
        ref = db.collection("users").document(doc_id)
        snap = DocumentSnapWrapper(ref)



        tg_id = _extract_provider_id(user_data.get("externalTg"))
        vk_id = _extract_provider_id(user_data.get("externalVk"))

        if not tg_id and not vk_id:
            return

        if await maybe_handle_autocharge(
            snap=snap,
            user_data=user_data,
            tg_id=tg_id,
            vk_id=vk_id,
            notify_telegram=_notify_telegram,
            notify_vk=_notify_vk,
            logger=logger,
        ):
            return

        current_end = user_data.get("subscriptionEndsAt")
        end_str = ""
        if hasattr(current_end, "strftime"):
            end_str = current_end.strftime("%d.%m.%Y")
        else:
            end_str = str(current_end)

        text = (
            f"⏳ Ваша подписка скоро закончится {end_str}.\n\n"
            "Что бы оставаться на связи и не потерять доступ в интернет, продлите подписку."
        )

        if tg_id:
            await _notify_telegram(tg_id, text)
        if vk_id:
            await _notify_vk(vk_id, text)

    except Exception:
        logger.exception("failed to handle user expiring soon event for %s", user_data.get("_doc_id"))


async def handle_user_retention_survey(db: firestore.Client, user_data: dict) -> None:
    try:
        current_end = user_data.get("subscriptionEndsAt")
        current_end_ms = _timestamp_ms(current_end) if current_end else None
        survey_sent_at_ms = _timestamp_ms(user_data.get("expirySurveySentAtMs"))

        if user_data.get("expirySurveySent"):
            if survey_sent_at_ms is None:
                # Legacy survey flag is set, and we don't have a timestamp. Assume already sent for this expiry.
                return
            if current_end_ms is not None and survey_sent_at_ms >= current_end_ms:
                # Already sent for current expiry
                return

        tg_id = _extract_provider_id(user_data.get("externalTg"))
        vk_id = _extract_provider_id(user_data.get("externalVk"))
        if not tg_id and not vk_id:
            return

        text = (
            "Ваша подписка закончилась и вы её не продлили🤔\n\n"
            "Помогите нам стать лучше. Ответьте на пару вопросов👇\n\n"
            "По какой причине вы не стали оформлять подписку?"
        )

        doc_id = user_data.get("_doc_id")
        ref = db.collection("users").document(doc_id)
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
            tokens = await asyncio.to_thread(get_vk_tokens_for_user, vk_id)
            for token in tokens:
                params = {
                    "user_id": vk_id,
                    "message": text,
                    "random_id": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
                    "keyboard": vk_kb,
                    "access_token": token,
                    "v": "5.231",
                }
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            "https://api.vk.com/method/messages.send", params=params
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if not data.get("error"):
                                    success = True
                except Exception:
                    logger.exception("Failed to send VK survey to user %s using token prefix %s", vk_id, token[:8])

        if success:
            update_fields = {"expirySurveySent": True}
            if current_end_ms is not None:
                update_fields["expirySurveySentAtMs"] = current_end_ms
            await asyncio.to_thread(ref.update, update_fields)
            logger.info("Sent expiry retention survey to user %s", doc_id)
    except Exception:
        logger.exception("failed to handle user retention survey for %s", user_data.get("_doc_id"))


async def handle_expiry_webhook_event(
    db: firestore.Client,
    user_data: dict,
    event_type: str,
    data: dict,
    meta: dict,
) -> None:
    offset = meta.get("expiration")
    if offset is not None:
        try:
            offset = int(offset)
        except (ValueError, TypeError):
            pass

    is_expiry = (event_type == "user.expired") or (event_type == "user.expiration" and offset == 0)
    is_pre_expiry = (event_type == "user.expiration" and isinstance(offset, int) and offset < 0)
    is_retention_survey = (event_type == "user.expiration" and offset == 24)

    if is_expiry:
        await handle_user_expired(db, user_data)
    elif is_pre_expiry:
        await handle_user_expiring_soon(db, user_data, offset)
    elif is_retention_survey:
        await handle_user_retention_survey(db, user_data)
    elif event_type == "user.not_connected":
        await handle_user_not_connected(db, user_data, meta)
    else:
        logger.info(
            "Ignored event '%s' with offset %s for user %s",
            event_type,
            offset,
            user_data.get("_doc_id"),
        )
