import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from vkbottle import API
from vkbottle.tools import PhotoMessageUploader

from mvm_bot.config import bot_token, vk_bot_tokens
from mvm_bot.firebase_client import (
    get_tg_cached_attachment,
    get_vk_cached_attachment,
    set_tg_cached_attachment,
    set_vk_cached_attachment,
    get_vk_tokens_for_user,
)


async def notify_telegram(user_id: str, text: str, *, logger) -> None:
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


async def notify_vk_with_token(user_id: str, text: str, *, logger) -> bool:
    tokens = await asyncio.to_thread(get_vk_tokens_for_user, user_id)
    if not tokens:
        logger.warning("vk notify: no tokens found for user %s", user_id)
        return False
    
    any_success = False
    for token in tokens:
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
                    "https://api.vk.com/method/messages.send",
                    params=params,
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.warning(
                            "vk notify failed (token=%s...): %s %s",
                            token[:8],
                            resp.status,
                            body,
                        )
                        continue
                    data = await resp.json()
                    if data.get("error"):
                        logger.warning(
                            "vk api error (token=%s...): %s",
                            token[:8],
                            data["error"],
                        )
                        continue
                    any_success = True
        except Exception:
            logger.exception("vk notify error for user %s (token=%s...)", user_id, token[:8])
            
    return any_success


async def notify_vk(user_id: str, text: str, *, logger) -> None:
    print(user_id)
    await notify_vk_with_token(user_id, text, logger=logger)



async def notify_telegram_photo(
    user_id: str,
    photo_path: Path,
    caption: str,
    *,
    logger,
    reply_markup: dict | None = None,
) -> bool:
    token = bot_token()
    cached_file_id = await get_tg_cached_attachment(token, [photo_path.name])

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        if cached_file_id:
            data = aiohttp.FormData()
            data.add_field("chat_id", str(user_id))
            data.add_field("caption", caption)
            data.add_field("parse_mode", "HTML")
            data.add_field("photo", cached_file_id)
            if reply_markup:
                data.add_field("reply_markup", json.dumps(reply_markup))

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        return True
                    body = await resp.text()
                    logger.warning(
                        "telegram notify photo with cached file_id failed, will try re-upload: %s %s",
                        resp.status,
                        body,
                    )

        data = aiohttp.FormData()
        data.add_field("chat_id", str(user_id))
        data.add_field("caption", caption)
        data.add_field("parse_mode", "HTML")
        if reply_markup:
            data.add_field("reply_markup", json.dumps(reply_markup))

        with open(photo_path, "rb") as photo_file:
            data.add_field("photo", photo_file, filename=photo_path.name)
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


async def notify_vk_photo(
    user_id: str,
    photo_path: Path,
    caption: str,
    *,
    logger,
    keyboard: str | None = None,
) -> bool:
    tokens = await asyncio.to_thread(get_vk_tokens_for_user, user_id)
    if not tokens:
        logger.warning("vk notify photo: no tokens found for user %s", user_id)
        return False

    any_success = False
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
                        "https://api.vk.com/method/messages.send",
                        params=params,
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if not data.get("error"):
                                any_success = True
                                continue
                            logger.warning("vk notify photo with cached attachment failed: %s", data["error"])

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
                    "https://api.vk.com/method/messages.send",
                    params=params,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if not data.get("error"):
                            any_success = True
        except Exception:
            logger.exception("vk notify photo error for user %s (token=%s...)", user_id, token[:8])

    if not any_success:
        logger.warning("vk notify photo: all tokens failed for user %s", user_id)
    return any_success



def build_vk_survey_keyboard() -> str:
    return json.dumps(
        {
            "inline": True,
            "buttons": [
                [{"action": {"type": "callback", "label": "Плохо работало", "payload": json.dumps({"c": "survey", "r": "bad"})}}],
                [{"action": {"type": "callback", "label": "Дорого", "payload": json.dumps({"c": "survey", "r": "expensive"})}}],
                [{"action": {"type": "callback", "label": "Пользуюсь другим VPN", "payload": json.dumps({"c": "survey", "r": "other_vpn"})}}],
                [{"action": {"type": "callback", "label": "Другое", "payload": json.dumps({"c": "survey", "r": "other"})}}],
                [{"action": {"type": "callback", "label": "Оформлю подписку чуть позже🫶", "payload": json.dumps({"c": "survey", "r": "later"})}}],
            ],
        }
    )
