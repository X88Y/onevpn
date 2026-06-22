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
            ),
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(f"❌ {text}")
