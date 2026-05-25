import asyncio
import logging
from datetime import datetime, timezone

from vkbottle import Callback, Keyboard, KeyboardButtonColor, OpenLink
from vkbottle.bot import Message
from vkbottle.tools import PhotoMessageUploader

from mvm_bot.config import vk_menu_banner_path
from mvm_bot.constants import SUBSCRIPTION_PLANS, SUPPORT_URL, TRIAL_FIELDS, VK_SUPPORT_URL
from mvm_bot.datetime_utils import as_utc_datetime
from mvm_bot.main_menu import main_menu_caption

_banner_attachments_cache = {}


def set_cached_banner(token: str, attachment: str) -> None:
    _banner_attachments_cache[token] = attachment


def get_cached_banner(token: str) -> str | None:
    return _banner_attachments_cache.get(token)


async def preupload_menu_banner(tokens: list[str]) -> None:
    banner = vk_menu_banner_path()
    if not banner or not tokens:
        return

    from vkbottle import API
    from vkbottle.tools import PhotoMessageUploader
    from mvm_bot.firebase_client import get_vk_cached_attachment, set_vk_cached_attachment

    for token in tokens:
        # Check Firestore cache first
        cached = await get_vk_cached_attachment(token, [banner.name])
        if cached:
            set_cached_banner(token, cached)
            logging.info(f"Loaded menu banner attachment ID from Firestore cache for token {token[:8]}: {cached}")
            continue

        api = API(token)
        uploader = PhotoMessageUploader(api)
        attempts = 5
        success = False
        for attempt in range(1, attempts + 1):
            try:
                logging.info(f"Pre-uploading menu banner for token {token[:8]} (attempt {attempt}/{attempts})...")
                attachment = await uploader.upload(file_source=str(banner))
                set_cached_banner(token, attachment)
                await set_vk_cached_attachment(token, [banner.name], attachment)
                logging.info(f"Successfully pre-uploaded banner for token {token[:8]} and saved to Firestore: {attachment}")
                success = True
                break
            except Exception as e:
                logging.error(f"Failed to pre-upload banner for token {token[:8]} (attempt {attempt}/{attempts}): {e}")
                if attempt < attempts:
                    await asyncio.sleep(3)
        if not success:
            logging.error(f"Failed to pre-upload banner for token {token[:8]} after all attempts.")


def _has_active_subscription(data: dict) -> bool:
    end = as_utc_datetime(data.get("subscriptionEndsAt"))
    if end is None:
        return False
    return end > datetime.now(timezone.utc)


async def main_menu_keyboard_json(vk_id: int, data: dict) -> str:
    is_active = _has_active_subscription(data)
    kb = Keyboard(inline=True)
    
    sub_url = data.get("remnawaveSubscriptionUrl")
    if sub_url:
        kb.add(
            OpenLink(
                label="🔗 Подключить",
                link=sub_url,
            )
        )
        if data.get(TRIAL_FIELDS["vk"]) is not True:
            kb.row()
            kb.add(Callback(label="🎁 Получить VPN бесплатно", payload={"c": "trial"}))
    else:
        if data.get(TRIAL_FIELDS["vk"]) is not True:
            kb.add(Callback(label="🎁 Получить VPN бесплатно", payload={"c": "trial"}))

    if kb.buttons:
        kb.row()

    kb.add(
        Callback(label="💳 Купить подписку", payload={"c": "buy"}),
        color=KeyboardButtonColor.POSITIVE if not is_active else None,
    )
    kb.row()
    kb.add(Callback(label="👥 Пригласить друзей", payload={"c": "invite"}))
    kb.row()
    kb.add(OpenLink(label="💬 Поддержка", link=VK_SUPPORT_URL))
    return kb.get_json()


def plan_selection_keyboard_json() -> str:
    p30 = SUBSCRIPTION_PLANS["plan_30"]
    p90 = SUBSCRIPTION_PLANS["plan_90"]
    kb = Keyboard(inline=True)
    kb.add(
        Callback(
            label=f"30 дней — {p30['rub']} ₽",
            payload={"c": "plan", "p": "plan_30"},
        )
    )
    kb.row()
    kb.add(
        Callback(
            label=f"90 дней — {p90['rub']} ₽",
            payload={"c": "plan", "p": "plan_90"},
        )
    )
    return kb.get_json()


def rub_checkout_keyboard_json(plan_key: str) -> str:
    plan = SUBSCRIPTION_PLANS[plan_key]
    kb = Keyboard(inline=True)
    kb.add(
        Callback(
            label=f"💳 ЮMoney карта — {plan['rub']} ₽",
            payload={"c": "pay", "p": plan_key, "m": "ym_card"},
        )
    )
    kb.row()
    kb.add(
        Callback(
            label=f"📲 СБП (ЮMoney) — {plan['rub']} ₽",
            payload={"c": "pay", "p": plan_key, "m": "ym_sbp"},
        ),
        color=KeyboardButtonColor.POSITIVE,
    )
    kb.row()
    kb.add(
        Callback(
            label=f"🔐 Crypto — {plan['rub']} ₽",
            payload={"c": "pay", "p": plan_key, "m": "rub"},
        )
    )
    kb.row()
    kb.add(
        Callback(
            label="🌐 Другие способы оплаты",
            payload={"c": "other_pay", "p": plan_key},
        )
    )
    return kb.get_json()


def other_checkout_keyboard_json(plan_key: str) -> str:
    plan = SUBSCRIPTION_PLANS[plan_key]
    kb = Keyboard(inline=True)
    kb.add(
        Callback(
            label=f"📲 СБП (QR) — {plan['rub']} ₽",
            payload={"c": "pay", "p": plan_key, "m": "fk_sbp"},
        )
    )
    kb.row()
    kb.add(
        Callback(
            label=f"💳 Карта РФ — {plan['rub']} ₽",
            payload={"c": "pay", "p": plan_key, "m": "fk_card"},
        )
    )
    kb.row()
    kb.add(
        Callback(
            label=f"💚 СберПэй — {plan['rub']} ₽",
            payload={"c": "pay", "p": plan_key, "m": "fk_sberpay"},
        )
    )
    kb.row()
    kb.add(
        Callback(
            label=f"🏦 СБП (Platega) — {plan['rub']} ₽",
            payload={"c": "pay", "p": plan_key, "m": "platega"},
        ),
        color=KeyboardButtonColor.POSITIVE,
    )
    kb.row()
    kb.add(
        Callback(
            label="« Назад",
            payload={"c": "plan", "p": plan_key},
        )
    )
    return kb.get_json()


async def send_main_menu(message: Message, data: dict) -> None:
    caption = main_menu_caption(data, platform="vk")
    keyboard = await main_menu_keyboard_json(message.from_id, data)
    banner = vk_menu_banner_path()
    if banner is not None:
        token = getattr(getattr(message.ctx_api, "token_generator", None), "token", None)
        cached_photo = get_cached_banner(token) if token else None

        # Check Firestore cache if not in memory
        if not cached_photo and token:
            from mvm_bot.firebase_client import get_vk_cached_attachment
            cached_photo = await get_vk_cached_attachment(token, [banner.name])
            if cached_photo:
                set_cached_banner(token, cached_photo)

        if cached_photo:
            try:
                await message.answer(message=caption, attachment=cached_photo, keyboard=keyboard)
                return
            except Exception:
                logging.exception("Failed to send main menu with cached banner")
        else:
            try:
                from mvm_bot.firebase_client import set_vk_cached_attachment
                uploader = PhotoMessageUploader(message.ctx_api)
                photo = await uploader.upload(
                    file_source=str(banner),
                    peer_id=message.peer_id,
                )
                if token:
                    set_cached_banner(token, photo)
                    await set_vk_cached_attachment(token, [banner.name], photo)
                await message.answer(message=caption, attachment=photo, keyboard=keyboard)
                return
            except Exception:
                logging.exception("VK banner upload failed, falling back to text-only menu")

    await message.answer(message=caption, keyboard=keyboard)
