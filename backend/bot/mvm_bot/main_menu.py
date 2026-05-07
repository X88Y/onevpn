from datetime import datetime, timezone

from aiogram.enums import ParseMode  # type: ignore[import-not-found]
from aiogram.types import (  # type: ignore[import-not-found]
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from mvm_bot.config import menu_banner_path
from mvm_bot.constants import PRIVACY_POLICY_URL, SUPPORT_URL, TERMS_URL, TRIAL_FIELDS
from mvm_bot.datetime_utils import as_utc_datetime
from mvm_bot.jwt_auth import connect_redirect_url


def _has_active_subscription(data: dict) -> bool:
    end = as_utc_datetime(data.get("subscriptionEndsAt"))
    if end is None:
        return False
    return end > datetime.now(timezone.utc)


def format_subscription_end(data: dict) -> str:
    end = as_utc_datetime(data.get("subscriptionEndsAt"))
    if end is None:
        return "⏸️ Не активна"

    now = datetime.now(timezone.utc)
    if end <= now:
        return f"⌛ Истекла {end:%d.%m.%Y}"

    return f"✅ Активна до {end:%d.%m.%Y}"


def main_menu_keyboard(tg_id: int, data: dict) -> InlineKeyboardMarkup:
    is_active = _has_active_subscription(data)
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="🔗 Подключить",
                url=connect_redirect_url(tg_id),
                **({"style": "primary"} if is_active else {}),
            )
        ],
    ]
    if data.get(TRIAL_FIELDS["tg"]) is not True:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🎁 Получить VPN бесплатно",
                    callback_data="menu:start_trial",
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="💳 Купить подписку",
                    callback_data="menu:buy_subscription",
                    **({"style": "success"} if not is_active else {}),
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Пригласить друзей",
                    callback_data="menu:invite_friends",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Поддержка",
                    url=SUPPORT_URL,
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_caption(data: dict, platform: str = "tg") -> str:
    caption = (
        "🛡️ MVM | Личный кабинет\n\n"
        "📅 Подписка:\n"
        f"{format_subscription_end(data)}\n\n"
    )
    if platform == "tg":
        caption += (
            f"<a href='{TERMS_URL}'>📋 Пользовательское соглашение</a>\n"
            f"<a href='{PRIVACY_POLICY_URL}'>🔒 Политика конфиденциальности</a>\n\n"
        )
    else:
        caption += (
            f"📋 Пользовательское соглашение:\n{TERMS_URL}\n"
            f"🔒 Политика конфиденциальности:\n{PRIVACY_POLICY_URL}\n\n"
        )

    caption += "👇 Выберите действие:"
    return caption


async def send_main_menu(message: Message, data: dict) -> None:
    if message.from_user is None:
        await message.answer("Cannot identify Telegram user.")
        return

    caption = main_menu_caption(data, platform="tg")
    keyboard = main_menu_keyboard(message.from_user.id, data)
    banner = menu_banner_path()
    if banner is not None:
        await message.answer_photo(
            FSInputFile(banner),
            caption=caption,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        return

    await message.answer(caption, reply_markup=keyboard, parse_mode=ParseMode.HTML)
