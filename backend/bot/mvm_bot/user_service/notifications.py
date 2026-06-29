import asyncio
import logging

import httpx
from aiogram import Bot  # type: ignore[import-not-found]

from mvm_bot.config import bot_token
from mvm_bot.firebase_client import get_vk_tokens_for_user

logger = logging.getLogger(__name__)


async def notify_tg_user(tg_id: str, text: str) -> None:
    try:
        async with Bot(token=bot_token()) as bot:
            await bot.send_message(chat_id=int(tg_id), text=text)
    except Exception:
        logger.exception("Failed to notify TG user %s", tg_id)


async def notify_vk_user(vk_id: str, text: str) -> None:
    tokens = await asyncio.to_thread(get_vk_tokens_for_user, vk_id)
    if not tokens:
        logger.warning("No VK bot tokens found for user %s", vk_id)
        return
    for token in tokens:
        try:
            params = {
                "user_id": int(vk_id),
                "message": text,
                "random_id": 0,
                "access_token": token,
                "v": "5.231"
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post("https://api.vk.com/method/messages.send", data=params)
                if resp.status_code == 200:
                    data = resp.json()
                    if "error" in data:
                        logger.warning("VK send error using token prefix %s: %s", token[:8], data["error"])
        except Exception:
            logger.exception("Failed to send VK message using token prefix %s", token[:8])


async def notify_referrer(referrer_data: dict, text: str) -> None:
    ext_tg = referrer_data.get("externalTg")
    ext_vk = referrer_data.get("externalVk")
    if ext_tg:
        tg_id = ext_tg.split(":")[-1]
        await notify_tg_user(tg_id, text)
    if ext_vk:
        vk_id = ext_vk.split(":")[-1]
        await notify_vk_user(vk_id, text)
