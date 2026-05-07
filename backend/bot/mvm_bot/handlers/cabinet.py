import asyncio
import logging

from aiogram import Bot, F, Router  # type: ignore[import-not-found]
from aiogram.enums import ParseMode  # type: ignore[import-not-found]
from aiogram.filters import CommandObject, CommandStart  # type: ignore[import-not-found]
from aiogram.fsm.context import FSMContext  # type: ignore[import-not-found]
from aiogram.fsm.state import State, StatesGroup  # type: ignore[import-not-found]
from aiogram.types import (  # type: ignore[import-not-found]
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from mvm_bot.config import (
    freekassa_api_key,
    freekassa_ip,
    freekassa_return_url,
    freekassa_shop_id,
    heleket_callback_url,
    heleket_merchant_uuid,
    heleket_payment_api_key,
    platega_failed_url,
    platega_merchant_id,
    platega_return_url,
    platega_secret,
)
from mvm_bot.constants import CONNECT_REDIRECT_ORIGIN, REFERRAL_BONUS_DAYS, SUBSCRIPTION_PLANS, TRIAL_DAYS
from mvm_bot.main_menu import (
    format_subscription_end,
    main_menu_keyboard,
    send_main_menu,
)
from mvm_bot.freekassa import PAYMENT_CARD_RU, PAYMENT_SBERPAY, PAYMENT_SBP
from mvm_bot.freekassa import checkout_url as freekassa_checkout_url
from mvm_bot.heleket import invoice_checkout_url
from mvm_bot.platega import transaction_checkout_url as platega_checkout_url
from mvm_bot.user_service import (
    apply_referral_code_tg,
    count_referrals,
    extend_subscription,
    grant_purchase_referral_bonus_tg,
    record_payment_checkout_click,
    save_telegram_user,
    start_telegram_trial,
)

router = Router()


class ReferralStates(StatesGroup):
    waiting_for_code = State()


def _plan_selection_keyboard() -> InlineKeyboardMarkup:
    p30 = SUBSCRIPTION_PLANS["plan_30"]
    p90 = SUBSCRIPTION_PLANS["plan_90"]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"30 дней — {p30['rub']} ₽",
                    callback_data="buy:plan_30",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"90 дней — {p90['rub']} ₽",
                    callback_data="buy:plan_90",
                ),
            ],
        ]
    )


def _payment_method_keyboard(plan_key: str) -> InlineKeyboardMarkup:
    plan = SUBSCRIPTION_PLANS[plan_key]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"⭐ Telegram Stars — {plan['stars']} ⭐",
                    callback_data=f"buy:{plan_key}:stars",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"📲 СБП (QR) — {plan['rub']} ₽",
                    callback_data=f"buy:{plan_key}:fk_sbp",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"💳 Карта РФ — {plan['rub']} ₽",
                    callback_data=f"buy:{plan_key}:fk_card",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"💚 СберПэй — {plan['rub']} ₽",
                    callback_data=f"buy:{plan_key}:fk_sberpay",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"🏦 СБП (Platega) — {plan['rub']} ₽",
                    callback_data=f"buy:{plan_key}:platega",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"🔐 Crypto — {plan['rub']} ₽",
                    callback_data=f"buy:{plan_key}:rub",
                ),
            ],
        ]
    )


@router.message(CommandStart())
async def start(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        await message.answer("Cannot identify Telegram user.")
        return

    referral_code = None
    if command.args and command.args.startswith("ref_"):
        referral_code = command.args[4:]

    _, data = await save_telegram_user(message.from_user, referral_code)
    await send_main_menu(message, data)


@router.callback_query(F.data == "menu:start_trial")
async def start_trial_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer("Cannot identify Telegram user.", show_alert=True)
        return

    _, data, activated = await start_telegram_trial(callback.from_user)
    if activated:
        providers = ", ".join(activated)
        days = TRIAL_DAYS * len(activated)
        await callback.answer(
            f"🎉 Пробный период активирован!\n"
            f"➕ +{days} дней ({providers}).",
            show_alert=True,
        )
    else:
        await callback.answer(
            "ℹ️ Бесплатный период уже был активирован ранее.",
            show_alert=True,
        )

    if callback.message and isinstance(callback.message, Message):
        if activated:
            confirm = (
                "✅ Подписка активирована\n\n"
                f"📅 {format_subscription_end(data)}\n\n"
                "Приятного пользования VPN! 🚀"
            )
        else:
            confirm = (
                f"📅 Подписка: {format_subscription_end(data)}\n\n"
                "Меню действий ниже 👇"
            )
        await callback.message.answer(
            confirm,
            reply_markup=main_menu_keyboard(callback.from_user.id, data),
        )


@router.callback_query(F.data == "menu:buy_subscription")
async def buy_subscription_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message and isinstance(callback.message, Message):
        await callback.message.answer(
            "Доступные варианты:",
            reply_markup=_plan_selection_keyboard(),
        )


@router.callback_query(F.data.startswith("buy:"))
async def select_plan_callback(callback: CallbackQuery, bot: Bot) -> None:
    if callback.data is None or callback.from_user is None:
        await callback.answer("Ошибка.", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) == 2:
        _, plan_key = parts
        plan = SUBSCRIPTION_PLANS.get(plan_key)
        if plan is None:
            await callback.answer("Неизвестный план.", show_alert=True)
            return
        await callback.answer()
        text = f"{plan['label']} — выберите способ оплаты:"
        kb = _payment_method_keyboard(plan_key)
        if callback.message and isinstance(callback.message, Message):
            await callback.message.answer(text, reply_markup=kb)
        else:
            await bot.send_message(chat_id=callback.from_user.id, text=text, reply_markup=kb)
        return

    if len(parts) != 3:
        await callback.answer("Ошибка данных.", show_alert=True)
        return

    _, plan_key, method = parts
    plan = SUBSCRIPTION_PLANS.get(plan_key)
    if plan is None:
        await callback.answer("Неизвестный план.", show_alert=True)
        return

    await callback.answer()

    if method == "stars":
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"VPN подписка — {plan['label']}",
            description=f"Доступ к VPN на {plan['days']} дней.",
            payload=plan_key,
            currency="XTR",
            prices=[LabeledPrice(label=plan["label"], amount=plan["stars"])],
        )
        return

    if method == "rub":
        uid = callback.from_user.id
        merchant_uuid = heleket_merchant_uuid()
        api_key = heleket_payment_api_key()
        ipn_url = heleket_callback_url()
        if not merchant_uuid or not api_key or not ipn_url:
            await bot.send_message(
                chat_id=uid,
                text=(
                    "Оплата сейчас недоступна. Напишите в поддержку: ссылка на оплату не сформировалась."
                ),
            )
            return
        rub = plan.get("rub")
        if rub is None:
            await bot.send_message(
                chat_id=uid,
                text="Для этого плана оплата не настроена.",
            )
            return
        try:
            inv = await invoice_checkout_url(
                merchant_uuid=merchant_uuid,
                api_key=api_key,
                ipn_callback_url=ipn_url,
                payer_user_id=uid,
                payer_provider="tg",
                plan_key=plan_key,
                price_amount=float(rub),
                price_currency="rub",
                success_url=CONNECT_REDIRECT_ORIGIN,
            )
            checkout = inv.url
        except Exception:
            logging.exception("Heleket invoice failed")
            await bot.send_message(
                chat_id=uid,
                text="Не удалось создать ссылку на оплату. Попробуйте позже или напишите в поддержку.",
            )
            return

        try:
            await asyncio.to_thread(
                record_payment_checkout_click,
                service="heleket",
                provider="tg",
                external_user_id=str(uid),
                plan_key=plan_key,
                amount=float(rub),
                currency="RUB",
                pay_url=checkout,
                channel="telegram",
                correlation_id=inv.order_id,
                payment_method="rub",
            )
        except Exception:
            logging.exception("Failed to log Heleket (rub) checkout click")

        pay = float(rub)
        await bot.send_message(
            chat_id=uid,
            text=(
                f"💳 Оплата — {plan['label']} ({pay:.0f} ₽)\n\n"
                "После оплаты подписка продлится автоматически (обычно несколько минут).\n\n"
                f"Ссылка: {checkout}"
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Оплатить", url=checkout)]
                ]
            ),
        )
        return

    if method == "platega":
        uid = callback.from_user.id
        merchant_id = platega_merchant_id()
        secret = platega_secret()
        if not merchant_id or not secret:
            await bot.send_message(
                chat_id=uid,
                text="Оплата картой сейчас недоступна. Напишите в поддержку.",
            )
            return
        rub = plan.get("rub")
        if rub is None:
            await bot.send_message(
                chat_id=uid,
                text="Для этого плана оплата не настроена.",
            )
            return
        try:
            pg = await platega_checkout_url(
                merchant_id=merchant_id,
                secret=secret,
                provider="tg",
                user_id=uid,
                plan_key=plan_key,
                amount=float(rub),
                currency="RUB",
                description=f"VPN {plan['label']}",
                return_url=platega_return_url(),
                failed_url=platega_failed_url(),
            )
            checkout = pg.url
        except Exception:
            logging.exception("Platega transaction failed")
            await bot.send_message(
                chat_id=uid,
                text="Не удалось создать ссылку на оплату. Попробуйте позже или напишите в поддержку.",
            )
            return

        try:
            await asyncio.to_thread(
                record_payment_checkout_click,
                service="platega",
                provider="tg",
                external_user_id=str(uid),
                plan_key=plan_key,
                amount=float(rub),
                currency="RUB",
                pay_url=checkout,
                channel="telegram",
                correlation_id=pg.payload,
                payment_method="platega",
            )
        except Exception:
            logging.exception("Failed to log Platega checkout click")

        await bot.send_message(
            chat_id=uid,
            text=(
                f"🏦 Оплата картой — {plan['label']} ({float(rub):.0f} ₽)\n\n"
                "После оплаты подписка продлится автоматически (обычно несколько минут).\n\n"
                f"Ссылка: {checkout}"
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Оплатить", url=checkout)]
                ]
            ),
        )
        return

    if method == "crypto":
        uid = callback.from_user.id
        merchant_uuid = heleket_merchant_uuid()
        api_key = heleket_payment_api_key()
        ipn_url = heleket_callback_url()
        if not merchant_uuid or not api_key or not ipn_url:
            await bot.send_message(
                chat_id=uid,
                text=(
                    "Оплата криптой сейчас недоступна. Напишите в поддержку."
                ),
            )
            return
        crypto_usd = plan.get("crypto_usd")
        if crypto_usd is None:
            await bot.send_message(
                chat_id=uid,
                text="Для этого плана крипто-оплата не настроена.",
            )
            return
        try:
            inv = await invoice_checkout_url(
                merchant_uuid=merchant_uuid,
                api_key=api_key,
                ipn_callback_url=ipn_url,
                payer_user_id=uid,
                payer_provider="tg",
                plan_key=plan_key,
                price_amount=float(crypto_usd),
                price_currency="usd",
                success_url=CONNECT_REDIRECT_ORIGIN,
            )
            checkout = inv.url
        except Exception:
            logging.exception("Heleket invoice failed")
            await bot.send_message(
                chat_id=uid,
                text="Не удалось выставить счёт. Попробуйте позже.",
            )
            return

        try:
            await asyncio.to_thread(
                record_payment_checkout_click,
                service="heleket",
                provider="tg",
                external_user_id=str(uid),
                plan_key=plan_key,
                amount=float(crypto_usd),
                currency="USD",
                pay_url=checkout,
                channel="telegram",
                correlation_id=inv.order_id,
                payment_method="crypto",
            )
        except Exception:
            logging.exception("Failed to log Heleket (crypto) checkout click")

        await bot.send_message(
            chat_id=uid,
            text=(
                f"💳 Крипто-оплата — {plan['label']} (${float(crypto_usd):.2f})\n\n"
                f"После оплаты подписка продлится автоматически (обычно несколько минут).\n\n"
                f"{checkout}"
            ),
        )
        return

    _FK_METHODS = {
        "fk_sbp": (PAYMENT_SBP, "📲 СБП (QR)"),
        "fk_card": (PAYMENT_CARD_RU, "💳 Банк. карта РФ"),
        "fk_sberpay": (PAYMENT_SBERPAY, "💚 СберПэй"),
    }
    if method in _FK_METHODS:
        uid = callback.from_user.id
        shop_id = freekassa_shop_id()
        api_key = freekassa_api_key()
        if not shop_id or not api_key:
            await bot.send_message(
                chat_id=uid,
                text="Оплата через FreeKassa сейчас недоступна. Напишите в поддержку.",
            )
            return
        rub = plan.get("rub")
        if rub is None:
            await bot.send_message(
                chat_id=uid,
                text="Для этого плана оплата не настроена.",
            )
            return
        payment_system, method_label = _FK_METHODS[method]
        try:
            fk = await freekassa_checkout_url(
                shop_id=shop_id,
                api_key=api_key,
                provider="tg",
                user_id=uid,
                plan_key=plan_key,
                payment_system=payment_system,
                email=f"{uid}@telegram.org",
                ip=freekassa_ip(),
                amount=float(rub),
            )
            checkout = fk.url
        except Exception:
            logging.exception("FreeKassa order creation failed")
            await bot.send_message(
                chat_id=uid,
                text="Не удалось создать ссылку на оплату. Попробуйте позже или напишите в поддержку.",
            )
            return

        try:
            await asyncio.to_thread(
                record_payment_checkout_click,
                service="freekassa",
                provider="tg",
                external_user_id=str(uid),
                plan_key=plan_key,
                amount=float(rub),
                currency="RUB",
                pay_url=checkout,
                channel="telegram",
                correlation_id=fk.payment_id,
                payment_method=method,
                payment_system=payment_system,
            )
        except Exception:
            logging.exception("Failed to log FreeKassa checkout click")

        await bot.send_message(
            chat_id=uid,
            text=(
                f"{method_label} — {plan['label']} ({float(rub):.0f} ₽)\n\n"
                "После оплаты подписка продлится автоматически (обычно несколько минут).\n\n"
                f"Ссылка: {checkout}"
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Оплатить", url=checkout)]
                ]
            ),
        )
        return

    await bot.send_message(
        chat_id=callback.from_user.id,
        text="Неизвестный способ оплаты.",
    )


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message) -> None:
    if message.from_user is None or message.successful_payment is None:
        return

    plan_key = message.successful_payment.invoice_payload
    plan = SUBSCRIPTION_PLANS.get(plan_key)
    if plan is None:
        await message.answer(
            "✅ Платёж получен, но план не распознан. Обратитесь в поддержку."
        )
        return

    _, data = await extend_subscription(message.from_user, plan["days"])

    try:
        await grant_purchase_referral_bonus_tg(message.from_user)
    except Exception:
        logging.exception("Failed to grant referral purchase bonus")

    await message.answer(
        f"🎉 Оплата прошла успешно!\n\n"
        f"✅ Подписка продлена на {plan['days']} дней.\n"
        f"📅 {format_subscription_end(data)}\n\n"
        "Приятного пользования VPN! 🚀",
        reply_markup=main_menu_keyboard(message.from_user.id, data),
    )


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
            f"• Зарегистрировался — вы получите +{REFERRAL_BONUS_DAYS} дня\n"
            f"• Совершил покупку — вы получите ещё +{REFERRAL_BONUS_DAYS} дня\n\n"
            f"Новый друг тоже получит +{REFERRAL_BONUS_DAYS} дня!",
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
