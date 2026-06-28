import asyncio

from aiogram import Bot, F, Router  # type: ignore[import-not-found]
from aiogram.enums import ParseMode  # type: ignore[import-not-found]
from aiogram.fsm.context import FSMContext  # type: ignore[import-not-found]
from aiogram.types import (  # type: ignore[import-not-found]
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from mvm_bot.constants import REFERRAL_BONUS_DAYS, REFERRAL_PURCHASE_BONUS_DAYS
from mvm_bot.handlers.cabinet_shared import PromoStates, ReferralStates, plan_selection_keyboard
from mvm_bot.promo_utils import extract_promo_candidate
from mvm_bot.user_service import (
    apply_promo_code_tg,
    apply_referral_code_tg,
    count_referrals,
    save_telegram_user,
)
from mvm_bot.user_service.promo import check_promo_code_validity

router = Router()


@router.callback_query(F.data == "menu:invite_friends")
async def invite_friends_callback(callback: CallbackQuery, bot: Bot) -> None:
    if callback.from_user is None:
        await callback.answer()
        return

    _, data = await save_telegram_user(callback.from_user)
    referral_code = data.get("referralCode")

    await callback.answer()

    if not referral_code:
        if callback.message and isinstance(callback.message, Message):
            await callback.message.answer("Не удалось получить реферальный код. Попробуйте позже.")
        return

    bot_info, invited_count = await asyncio.gather(
        bot.get_me(),
        count_referrals(referral_code),
    )
    referral_link = f"https://t.me/{bot_info.username}?start=ref_{referral_code}"
    already_referred = bool(data.get("referredByCode"))

    if callback.message and isinstance(callback.message, Message):
        await callback.message.answer(
            f"👥 <b>Пригласите друзей и получайте бонусы!</b>\n\n"
            f"📊 Приглашено друзей: <b>{invited_count}</b>\n\n"
            f"🔗 Ваша реферальная ссылка (нажмите, чтобы скопировать):\n"
            f"<code>{referral_link}</code>\n\n"
            f"🔑 Ваш реферальный код:\n"
            f"<code>ref_{referral_code}</code>\n\n"
            f"🎁 За каждого приглашённого друга:\n"
            f"• Зарегистрировался — вы получите +{REFERRAL_BONUS_DAYS} дней\n"
            f"• Совершил покупку — вы получите ещё +{REFERRAL_PURCHASE_BONUS_DAYS} дней\n\n"
            f"Новый друг тоже получит +{REFERRAL_BONUS_DAYS} дней!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    *(
                        []
                        if already_referred
                        else [
                            [
                                InlineKeyboardButton(
                                    text="✏️ Ввести код друга",
                                    callback_data="referral:enter_code",
                                )
                            ]
                        ]
                    )
                ]
            ),
        )


@router.callback_query(F.data == "referral:enter_code")
async def enter_referral_code_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(ReferralStates.waiting_for_code)
    if callback.message and isinstance(callback.message, Message):
        await callback.message.answer(
            "✏️ Введите реферальный код друга.\n\n"
            "Код выглядит так: <code>ref_a1b2c3d4</code>\n"
            "Можно ввести как с приставкой <code>ref_</code>, так и без неё.",
            parse_mode=ParseMode.HTML,
        )


@router.message(ReferralStates.waiting_for_code)
async def process_referral_code_input(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user is None or not message.text:
        return

    raw = message.text.strip()
    code = raw[4:] if raw.startswith("ref_") else raw

    success, text = await apply_referral_code_tg(message.from_user, code)
    await message.answer(f"{'✅' if success else '❌'} {text}")


@router.callback_query(F.data == "promo:enter_code")
async def enter_promo_code_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(PromoStates.waiting_for_promo)
    if callback.message and isinstance(callback.message, Message):
        await callback.message.answer(
            "🎟️ <b>Введите промокод:</b>",
            parse_mode=ParseMode.HTML,
        )


@router.message(PromoStates.waiting_for_promo)
async def process_promo_code_input(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user is None or not message.text:
        return

    raw = message.text.strip()
    code = raw.upper()

    success, text = await apply_promo_code_tg(message.from_user, code)
    if success:
        _, data = await save_telegram_user(message.from_user)
        await message.answer(
            text,
            reply_markup=plan_selection_keyboard(
                promo_activated=True,
                promo_discount=data.get("promoDiscount"),
                user_data=data,
            ),
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(f"❌ {text}")


@router.message(F.text)
async def auto_detect_promo_from_message(message: Message, state: FSMContext) -> None:
    if message.from_user is None or not message.text:
        return

    if await state.get_state() is not None:
        return

    candidate, explicit_prefix = extract_promo_candidate(message.text)
    if candidate is None:
        return

    is_valid, _ = await check_promo_code_validity(candidate)
    if not is_valid:
        if explicit_prefix:
            await message.answer("❌ Неверный или неактивный промокод.")
        return

    await save_telegram_user(message.from_user)
    success, text = await apply_promo_code_tg(message.from_user, candidate)
    if success:
        _, data = await save_telegram_user(message.from_user)
        await message.answer(
            text,
            reply_markup=plan_selection_keyboard(
                promo_activated=True,
                promo_discount=data.get("promoDiscount"),
                user_data=data,
            ),
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(f"❌ {text}")


@router.callback_query(F.data == "promo:delete_card_confirm")
async def delete_card_confirm_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message and isinstance(callback.message, Message):
        await callback.message.answer(
            "🗑️ Вы уверены, что хотите удалить привязанную карту?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Да, удалить", callback_data="promo:delete_card_yes"),
                        InlineKeyboardButton(text="🚫 Не удалять", callback_data="promo:delete_card_no"),
                    ]
                ]
            ),
        )


@router.callback_query(F.data == "promo:delete_card_yes")
async def delete_card_yes_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer("Ошибка идентификации пользователя.", show_alert=True)
        return

    from mvm_bot.firebase_client import init_firebase
    from mvm_bot.user_service.helpers import telegram_uid

    db = init_firebase()
    auth_uid = telegram_uid(callback.from_user.id)
    users_ref = db.collection("users")

    def perform_update():
        docs = users_ref.where("externalTg", "in", [auth_uid, str(callback.from_user.id)]).limit(1).get()
        if docs:
            docs[0].reference.update({
                "cardDeleted": True,
                "autoRenewalEnabled": False
            })

    await asyncio.to_thread(perform_update)
    await callback.answer("💳 Карта успешно удалена!", show_alert=True)

    # Delete the confirmation message
    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.delete()
        except Exception:
            pass


@router.callback_query(F.data == "promo:delete_card_no")
async def delete_card_no_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    # Delete the confirmation message
    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.delete()
        except Exception:
            pass



def subscription_management_keyboard(promo_activated: bool = False) -> InlineKeyboardMarkup:
    promo_btn_text = "🎟️ Изменить промокод" if promo_activated else "🎟️ Ввести промокод"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Включить автоплатеж", callback_data="sub:toggle_on"),
            ],
            [
                InlineKeyboardButton(text="❌ Выключить автоплатеж", callback_data="sub:toggle_off"),
            ],
            [
                InlineKeyboardButton(text="⏰ Настроить дни", callback_data="sub:set_days"),
            ],
            [
                InlineKeyboardButton(text="💳 Удалить карту", callback_data="promo:delete_card_confirm"),
            ],
            [
                InlineKeyboardButton(text="« Назад", callback_data="menu:buy_subscription")
            ],
        ]
    )


def renewal_days_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1 день", callback_data="sub:days:1")],
            [InlineKeyboardButton(text="3 дня", callback_data="sub:days:3")],
            [InlineKeyboardButton(text="14 дней", callback_data="sub:days:14")],
            [InlineKeyboardButton(text="« Назад", callback_data="sub:manage")],
        ]
    )


def get_subscription_status_text(data: dict) -> str:
    from mvm_bot.main_menu import format_subscription_end
    sub_end = format_subscription_end(data)
    auto_pay = "✅ Включен" if data.get("autoRenewalEnabled") is True else "❌ Выключен"
    days_val = data.get("renewalDaysBefore", 3)
    days_map = {1: "1 день", 3: "3 дня", 14: "14 дней"}
    days_str = days_map.get(days_val, f"{days_val} дн.")

    return (
        "📋 <b>Управление подпиской</b>\n\n"
        f"📅 <b>Подписка:</b> {sub_end}\n"
        f"💳 <b>Автоплатеж:</b> {auto_pay}\n"
        f"⏰ <b>Списание за:</b> {days_str} до окончания"
    )


@router.callback_query(F.data == "sub:manage")
async def subscription_manage_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.from_user is None:
        return
    _, data = await save_telegram_user(callback.from_user)
    status_text = get_subscription_status_text(data)

    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                status_text,
                reply_markup=subscription_management_keyboard(data.get("promoActivated", False)),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await callback.message.answer(
                status_text,
                reply_markup=subscription_management_keyboard(data.get("promoActivated", False)),
                parse_mode=ParseMode.HTML,
            )


@router.callback_query(F.data == "sub:set_days")
async def subscription_set_days_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                "⏰ Выберите за сколько дней до окончания списывать средства:",
                reply_markup=renewal_days_keyboard(),
            )
        except Exception:
            await callback.message.answer(
                "⏰ Выберите за сколько дней до окончания списывать средства:",
                reply_markup=renewal_days_keyboard(),
            )


@router.callback_query(F.data.startswith("sub:days:"))
async def subscription_days_selected_callback(callback: CallbackQuery) -> None:
    if callback.data is None:
        await callback.answer()
        return

    days_str = callback.data.split(":")[-1]
    days_map = {"1": "1 день", "3": "3 дня", "14": "14 дней"}
    label = days_map.get(days_str, days_str)

    if callback.from_user is not None:
        from mvm_bot.firebase_client import init_firebase
        from mvm_bot.user_service.helpers import telegram_uid

        db = init_firebase()
        auth_uid = telegram_uid(callback.from_user.id)
        users_ref = db.collection("users")
        tg_id_str = str(callback.from_user.id)

        def save_days():
            docs = users_ref.where("externalTg", "in", [auth_uid, tg_id_str]).limit(1).get()
            if docs:
                docs[0].reference.update({"renewalDaysBefore": int(days_str)})

        await asyncio.to_thread(save_days)

    await callback.answer(f"✅ Установлено: списывать за {label} до окончания", show_alert=True)
    _, data = await save_telegram_user(callback.from_user)
    status_text = get_subscription_status_text(data)

    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                status_text,
                reply_markup=subscription_management_keyboard(data.get("promoActivated", False)),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


@router.callback_query(F.data == "sub:toggle_on")
async def subscription_toggle_on_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return

    from mvm_bot.firebase_client import init_firebase
    from mvm_bot.user_service.helpers import telegram_uid

    db = init_firebase()
    auth_uid = telegram_uid(callback.from_user.id)
    users_ref = db.collection("users")
    tg_id_str = str(callback.from_user.id)

    user_docs = await asyncio.to_thread(
        lambda: users_ref.where("externalTg", "in", [auth_uid, tg_id_str]).limit(1).get()
    )
    if user_docs:
        user_data = user_docs[0].to_dict() or {}
        if user_data.get("cardDeleted") is True:
            await callback.answer("❌ Невозможно включить автоплатеж: карта удалена.", show_alert=True)
            return

        def save_toggle():
            user_docs[0].reference.update({"autoRenewalEnabled": True})

        await asyncio.to_thread(save_toggle)
        await callback.answer("✅ Подписка включена!", show_alert=True)
    else:
        await callback.answer("❌ Пользователь не найден.", show_alert=True)


@router.callback_query(F.data == "sub:toggle_off")
async def subscription_toggle_off_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message and isinstance(callback.message, Message):
        await callback.message.answer(
            "🗑️ Вы уверены, что хотите выключить автоплатеж?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Да, выключить", callback_data="sub:toggle_off_yes"),
                        InlineKeyboardButton(text="🚫 Отмена", callback_data="sub:toggle_off_no"),
                    ]
                ]
            ),
        )


@router.callback_query(F.data == "sub:toggle_off_yes")
async def subscription_toggle_off_yes_callback(callback: CallbackQuery) -> None:
    if callback.from_user is not None:
        from mvm_bot.firebase_client import init_firebase
        from mvm_bot.user_service.helpers import telegram_uid

        db = init_firebase()
        auth_uid = telegram_uid(callback.from_user.id)
        users_ref = db.collection("users")
        tg_id_str = str(callback.from_user.id)

        def save_toggle():
            docs = users_ref.where("externalTg", "in", [auth_uid, tg_id_str]).limit(1).get()
            if docs:
                docs[0].reference.update({"autoRenewalEnabled": False})

        await asyncio.to_thread(save_toggle)

    await callback.answer("❌ Подписка выключена!", show_alert=True)

    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.delete()
        except Exception:
            pass


@router.callback_query(F.data == "sub:toggle_off_no")
async def subscription_toggle_off_no_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.delete()
        except Exception:
            pass
