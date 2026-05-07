from datetime import datetime, timezone

from vkbottle import Callback, Keyboard, KeyboardButtonColor, OpenLink
from vkbottle.bot import Message
from vkbottle.tools import PhotoMessageUploader

from mvm_bot.config import vk_menu_banner_path
from mvm_bot.constants import SUBSCRIPTION_PLANS, SUPPORT_URL, TRIAL_FIELDS
from mvm_bot.datetime_utils import as_utc_datetime
from mvm_bot.jwt_auth import connect_redirect_url_vk
from mvm_bot.main_menu import main_menu_caption


def _has_active_subscription(data: dict) -> bool:
    end = as_utc_datetime(data.get("subscriptionEndsAt"))
    if end is None:
        return False
    return end > datetime.now(timezone.utc)


def main_menu_keyboard_json(vk_id: int, data: dict) -> str:
    is_active = _has_active_subscription(data)
    kb = Keyboard(inline=True)
    kb.add(
        OpenLink(
            label="🔗 Подключить",
            link=connect_redirect_url_vk(vk_id),
        ),
        color=KeyboardButtonColor.PRIMARY if is_active else None,
    )
    if data.get(TRIAL_FIELDS["vk"]) is not True:
        kb.row()
        kb.add(Callback(label="🎁 Получить VPN бесплатно", payload={"c": "trial"}))
    kb.row()
    kb.add(
        Callback(label="💳 Купить подписку", payload={"c": "buy"}),
        color=KeyboardButtonColor.POSITIVE if not is_active else None,
    )
    kb.row()
    kb.add(Callback(label="👥 Пригласить друзей", payload={"c": "invite"}))
    kb.row()
    kb.add(OpenLink(label="💬 Поддержка", link=SUPPORT_URL))
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
            label=f"🏦 СБП — {plan['rub']} ₽",
            payload={"c": "pay", "p": plan_key, "m": "platega"},
        ),
        color=KeyboardButtonColor.PRIMARY,
    )
    kb.row()
    kb.add(
        Callback(
            label=f"💳 Crypto — {plan['rub']} ₽",
            payload={"c": "pay", "p": plan_key, "m": "rub"},
        )
    )
    return kb.get_json()


async def send_main_menu(message: Message, data: dict) -> None:
    caption = main_menu_caption(data, platform="vk")
    keyboard = main_menu_keyboard_json(message.from_id, data)
    banner = vk_menu_banner_path()
    if banner is not None:
        uploader = PhotoMessageUploader(message.ctx_api)
        photo = await uploader.upload(
            file_source=str(banner),
            peer_id=message.peer_id,
        )
        await message.answer(message=caption, attachment=photo, keyboard=keyboard)
        return

    await message.answer(message=caption, keyboard=keyboard)
