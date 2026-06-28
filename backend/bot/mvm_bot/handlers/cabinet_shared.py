from aiogram import Bot  # type: ignore[import-not-found]
from aiogram.enums import ParseMode  # type: ignore[import-not-found]
from aiogram.fsm.context import FSMContext  # type: ignore[import-not-found]
from aiogram.fsm.state import State, StatesGroup  # type: ignore[import-not-found]
from aiogram.types import (  # type: ignore[import-not-found]
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from mvm_bot.constants import MANUAL_DIR, SUBSCRIPTION_PLANS, SUPPORT_URL
from mvm_bot.firebase_client import get_tg_cached_attachment, set_tg_cached_attachment
from mvm_bot.promo_utils import promo_multiplier
from mvm_bot.support_content import SUPPORT_ROOT_BUTTONS, VPN_ERROR_BUTTONS


class ReferralStates(StatesGroup):
    waiting_for_code = State()


class PromoStates(StatesGroup):
    waiting_for_promo = State()


def plan_selection_keyboard(
    promo_activated: bool = False,
    promo_discount: object | None = None,
    user_data: dict | None = None,
) -> InlineKeyboardMarkup:
    promo_factor = promo_multiplier(
        promo_activated,
        promo_discount,
        default_discount=0.0,
    )
    rows: list[list[InlineKeyboardButton]] = []
    for plan_key in ["std_30", "std_90", "prem_30", "prem_90"]:
        plan = SUBSCRIPTION_PLANS[plan_key]
        if promo_activated:
            original_rub = plan["rub"]
            discounted_rub = int(original_rub * promo_factor)
            struck_rub = "".join(char + "\u0336" for char in str(original_rub))
            text = f"{plan['emoji']} {plan['label']} — {struck_rub}₽/{discounted_rub}₽ — {plan['tier_label']}"
        else:
            text = f"{plan['emoji']} {plan['label']} — {plan['rub']} ₽ — {plan['tier_label']}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"buy:{plan_key}",
                ),
            ]
        )

    is_active = False
    if user_data:
        from mvm_bot.main_menu import has_active_subscription
        is_active = has_active_subscription(user_data)

    if is_active:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📋 Управление подпиской",
                    callback_data="sub:manage",
                )
            ]
        )
        promo_btn_text = "🎟️ Изменить промокод" if promo_activated else "🎟️ Ввести промокод"
        rows.append(
            [
                InlineKeyboardButton(
                    text="« Назад",
                    callback_data="menu:main",
                ),
                InlineKeyboardButton(
                    text=promo_btn_text,
                    callback_data="promo:enter_code",
                ),
            ]
        )
    else:
        if promo_activated:
            promo_btn_text = "🎟️ Изменить промокод"
            promo_callback = "promo:enter_code"
        else:
            promo_btn_text = "🎟️ Ввести промокод"
            promo_callback = "promo:enter_code"

        rows.append(
            [
                InlineKeyboardButton(
                    text=promo_btn_text,
                    callback_data=promo_callback,
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="« Назад",
                    callback_data="menu:main",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_method_keyboard(
    plan_key: str,
    promo_activated: bool = False,
    promo_discount: object | None = None,
) -> InlineKeyboardMarkup:
    plan = SUBSCRIPTION_PLANS[plan_key]
    rub = plan["rub"]
    stars = plan["stars"]
    promo_factor = promo_multiplier(
        promo_activated,
        promo_discount,
        default_discount=0.0,
    )
    if promo_activated:
        rub = int(rub * promo_factor)
        stars = int(stars * promo_factor)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"⭐ Telegram Stars — {stars} ⭐",
                    callback_data=f"buy:{plan_key}:stars",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"💳 ЮMoney карта — {rub} ₽",
                    callback_data=f"buy:{plan_key}:ym_card",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"📲 СБП (QR) — {rub} ₽",
                    callback_data=f"buy:{plan_key}:ym_sbp",
                    **{"style": "success"},
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"🔐 Crypto — {rub} ₽",
                    callback_data=f"buy:{plan_key}:rub",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Другие способы оплаты",
                    callback_data=f"buy_other:{plan_key}",
                ),
            ],
        ]
    )


def other_payment_method_keyboard(
    plan_key: str,
    promo_activated: bool = False,
    promo_discount: object | None = None,
) -> InlineKeyboardMarkup:
    plan = SUBSCRIPTION_PLANS[plan_key]
    rub = plan["rub"]
    promo_factor = promo_multiplier(
        promo_activated,
        promo_discount,
        default_discount=0.0,
    )
    if promo_activated:
        rub = int(rub * promo_factor)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📲 СБП (FK) — {rub} ₽",
                    callback_data=f"buy:{plan_key}:fk_sbp",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"💳 Карта РФ — {rub} ₽",
                    callback_data=f"buy:{plan_key}:fk_card",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"💚 СберПэй — {rub} ₽",
                    callback_data=f"buy:{plan_key}:fk_sberpay",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"🏦 СБП (Platega) — {rub} ₽",
                    callback_data=f"buy:{plan_key}:platega",
                    **{"style": "success"},
                ),
            ],
            [
                InlineKeyboardButton(
                    text="« Назад",
                    callback_data=f"buy:{plan_key}",
                ),
            ],
        ]
    )


def devices_keyboard(devices: list) -> InlineKeyboardMarkup:
    rows = []
    for dev in devices:
        if isinstance(dev, dict):
            hwid = dev.get("hwid")
            model = dev.get("deviceModel") or dev.get("device_model") or dev.get("hwid") or "Device"
            if hwid:
                btn_name = model[:20] + "..." if len(model) > 20 else model
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"❌ Удалить {btn_name}",
                            callback_data=f"dev:del:{hwid}",
                        )
                    ]
                )
    rows.append(
        [
            InlineKeyboardButton(
                text="« Назад",
                callback_data="menu:main",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=topic.label, callback_data=topic.tg_callback)]
        for topic in SUPPORT_ROOT_BUTTONS
    ]
    rows.append([InlineKeyboardButton(text="Написать агенту поддержки", url=SUPPORT_URL)])
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_vpn_errors_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=topic.label, callback_data=topic.tg_callback)]
        for topic in VPN_ERROR_BUTTONS
    ]
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="menu:support")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def cleanup_support_media(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    media_ids = data.get("support_media_ids")
    if media_ids:
        for mid in media_ids:
            try:
                await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=mid)
            except Exception:
                pass
        await state.update_data(support_media_ids=None)


async def send_support_answer(
    callback: CallbackQuery,
    state: FSMContext,
    text: str,
    photos: list[str],
    back_callback: str = "menu:support",
    back_label: str = "« К списку вопросов",
) -> None:
    await cleanup_support_media(callback, state)
    try:
        await callback.message.delete()
    except Exception:
        pass

    bot: Bot = callback.bot
    chat_id = callback.message.chat.id
    token = bot.token

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=back_label, callback_data=back_callback)],
            [InlineKeyboardButton(text="« В главное меню", callback_data="menu:main")],
            [InlineKeyboardButton(text="Написать агенту поддержки", url=SUPPORT_URL)],
        ]
    )

    media_ids = []

    if not photos:
        sent_msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        media_ids.append(sent_msg.message_id)
    elif len(photos) == 1:
        photo_filename = photos[0]
        cached_file_id = await get_tg_cached_attachment(token, [photo_filename])
        if cached_file_id:
            photo_input = cached_file_id
        else:
            photo_input = FSInputFile(MANUAL_DIR / photo_filename)

        sent_msg = await bot.send_photo(
            chat_id=chat_id,
            photo=photo_input,
            caption=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        if not cached_file_id and sent_msg.photo:
            file_id = sent_msg.photo[-1].file_id
            await set_tg_cached_attachment(token, [photo_filename], file_id)
        media_ids.append(sent_msg.message_id)
    else:
        media_group = []
        for photo_filename in photos:
            cached_file_id = await get_tg_cached_attachment(token, [photo_filename])
            if cached_file_id:
                media_group.append(InputMediaPhoto(media=cached_file_id))
            else:
                media_group.append(InputMediaPhoto(media=FSInputFile(MANUAL_DIR / photo_filename)))

        sent_media_msgs = await bot.send_media_group(chat_id=chat_id, media=media_group)

        for photo_filename, msg in zip(photos, sent_media_msgs):
            cached_file_id = await get_tg_cached_attachment(token, [photo_filename])
            if not cached_file_id and msg.photo:
                file_id = msg.photo[-1].file_id
                await set_tg_cached_attachment(token, [photo_filename], file_id)
            media_ids.append(msg.message_id)

        sent_text_msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        media_ids.append(sent_text_msg.message_id)

    await state.update_data(support_media_ids=media_ids)


async def send_support_submenu(
    callback: CallbackQuery,
    state: FSMContext,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    await cleanup_support_media(callback, state)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
