from datetime import datetime, timezone
from html import escape

from aiogram import Bot  # type: ignore[import-not-found]
from aiogram.enums import ParseMode  # type: ignore[import-not-found]
from aiogram.types import (  # type: ignore[import-not-found]
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from mvm_bot.config import menu_banner_path
from mvm_bot.constants import (
    PRIVACY_POLICY_URL,
    SITE_LINKS,
    SUPPORT_URL,
    TERMS_URL,
    TRIAL_FIELDS,
    VK_PRIVACY_POLICY_URL,
    VK_TERMS_URL,
)
from mvm_bot.datetime_utils import as_utc_datetime

_tg_banner_cache: dict[str, str] = {}


def set_cached_banner(token: str, file_id: str) -> None:
    _tg_banner_cache[token] = file_id


def get_cached_banner(token: str) -> str | None:
    return _tg_banner_cache.get(token)


async def preload_menu_banner(bot: Bot) -> None:
    banner = menu_banner_path()
    if not banner:
        return

    import logging
    from mvm_bot.firebase_client import get_tg_cached_attachment
    token = bot.token
    try:
        cached = await get_tg_cached_attachment(token, [banner.name])
        if cached:
            set_cached_banner(token, cached)
            logging.info(f"Loaded Telegram menu banner file_id from Firestore cache: {cached}")
        else:
            logging.info("No cached Telegram banner found in Firestore. It will be uploaded on the first user interaction.")
    except Exception as e:
        logging.error(f"Failed to preload Telegram menu banner: {e}")



def has_active_subscription(data: dict) -> bool:
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


async def main_menu_keyboard(tg_id: int, data: dict) -> InlineKeyboardMarkup:
    is_active = has_active_subscription(data)
    rows: list[list[InlineKeyboardButton]] = []
    sub_url = data.get("remnawaveSubscriptionUrl")
    if is_active and sub_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔗 Подключить",
                    url=sub_url,
                    **{"style": "primary"},
                )
            ]
        )
    if data.get(TRIAL_FIELDS["tg"]) is not True:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🎁 Получить VPN бесплатно",
                    callback_data="menu:start_trial",
                    **{"style": "success"},
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="💳 Купить подписку",
                callback_data="menu:buy_subscription",
                **({"style": "success"} if not is_active else {}),
            )
        ]
    )
    if is_active:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📱 Мои устройства",
                    callback_data="menu:devices",
                )
            ]
        )
    rows.extend(
        [
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


def main_menu_caption(data: dict, platform: str = "tg", remnawave_devices: list | None = None) -> str:
    tier = data.get("subscriptionTier")
    devices = remnawave_devices if remnawave_devices is not None else []
    devices_count = len(devices)

    if tier == "premium":
        tier_part = f"💎 Premium ({devices_count}/7)"
    else:
        tier_part = f"🤩 Standart ({devices_count}/1)"

    devices_part = "нет"
    if devices:
        devices_names = []
        for dev in devices:
            if isinstance(dev, dict):
                model = dev.get("deviceModel") or dev.get("device_model")
                plat = dev.get("platform")
                os_v = dev.get("osVersion") or dev.get("os_version")
                parts = []
                if model:
                    parts.append(model)
                if plat:
                    parts.append(plat)
                if os_v:
                    parts.append(os_v)

                if parts:
                    devices_names.append(" ".join(parts))
                else:
                    devices_names.append(dev.get("hwid") or "Unknown Device")
        if devices_names:
            devices_part = ", ".join(devices_names)

    caption = (
        "🛡️ MVM | Личный кабинет\n\n"
        f"📅 Подписка: {tier_part}\n"
        f"{format_subscription_end(data)}\n\n"
    )

    if platform == "tg":
        caption += (
            f"<a href='{escape(TERMS_URL)}'>📋 Пользовательское соглашение</a>\n"
            f"<a href='{escape(PRIVACY_POLICY_URL)}'>🔒 Политика конфиденциальности</a>\n\n"
        )
    elif platform == "vk":
        caption += (
            f"[{VK_TERMS_URL}|📋 Пользовательское соглашение]\n"
            f"[{VK_PRIVACY_POLICY_URL}|🔒 Политика конфиденциальности]\n\n"
        )
    else:
        caption += (
            f"📋 Пользовательское соглашение:\n{TERMS_URL}\n"
            f"🔒 Политика конфиденциальности:\n{PRIVACY_POLICY_URL}\n\n"
        )

    if SITE_LINKS:
        if platform == "tg":
            links_text = "\n".join(
                f"<a href='https://{link}'>{link}</a>" for link in SITE_LINKS
            )
        else:
            links_text = "\n".join(f"https://{link}" for link in SITE_LINKS)
        caption += f"🌐 Резерв:\n{links_text}\n\n"

    sub_url = data.get("remnawaveSubscriptionUrl")
    if sub_url and has_active_subscription(data):
        if platform == "tg":
            caption += f"🔗 Ключ подключения:\n<a href='{escape(sub_url)}'>{escape(sub_url)}</a>\n\n"
        else:
            caption += f"🔗 Ключ подключения:\n{sub_url}\n\n"

    caption += "👇 Выберите действие:"
    return caption


async def send_main_menu(message: Message, data: dict, user: User | None = None) -> None:
    actual_user = user or message.from_user
    if actual_user is None:
        await message.answer("Cannot identify Telegram user.")
        return

    rw_uuid = data.get("remnawaveUuid")
    devices = []
    if rw_uuid:
        try:
            from mvm_bot.remnawave_client import get_user_hwid_devices
            devices = await get_user_hwid_devices(rw_uuid)
        except Exception:
            import logging
            logging.exception("Failed to fetch Remnawave devices for main menu")

    caption = main_menu_caption(data, platform="tg", remnawave_devices=devices)
    keyboard = await main_menu_keyboard(actual_user.id, data)
    banner = menu_banner_path()
    if banner is not None:
        token = message.bot.token if message.bot else None
        cached_photo = get_cached_banner(token) if token else None

        # Check Firestore cache if not in memory
        if not cached_photo and token:
            from mvm_bot.firebase_client import get_tg_cached_attachment
            cached_photo = await get_tg_cached_attachment(token, [banner.name])
            if cached_photo:
                set_cached_banner(token, cached_photo)

        if cached_photo:
            try:
                await message.answer_photo(
                    cached_photo,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
                return
            except Exception:
                import logging
                logging.exception("Failed to send main menu with cached Telegram banner")

        # Fallback to uploading
        try:
            sent_message = await message.answer_photo(
                FSInputFile(banner),
                caption=caption,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            if token and sent_message.photo:
                file_id = sent_message.photo[-1].file_id
                set_cached_banner(token, file_id)
                from mvm_bot.firebase_client import set_tg_cached_attachment
                await set_tg_cached_attachment(token, [banner.name], file_id)
            return
        except Exception:
            import logging
            logging.exception("Telegram banner upload failed, falling back to text-only menu")

    await message.answer(caption, reply_markup=keyboard, parse_mode=ParseMode.HTML)

