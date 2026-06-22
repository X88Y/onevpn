import asyncio
import logging
import re

from aiogram import Bot, F, Router  # type: ignore[import-not-found]
from aiogram.enums import ParseMode  # type: ignore[import-not-found]
from aiogram.filters import CommandObject, CommandStart  # type: ignore[import-not-found]
from aiogram.fsm.context import FSMContext  # type: ignore[import-not-found]
from aiogram.fsm.state import State, StatesGroup  # type: ignore[import-not-found]
from aiogram.types import (  # type: ignore[import-not-found]
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
    InputMediaPhoto,
    FSInputFile,
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
    yoomoney_receiver,
    yoomoney_return_url,
)
from mvm_bot.constants import CONNECT_REDIRECT_ORIGIN, REFERRAL_BONUS_DAYS, REFERRAL_PURCHASE_BONUS_DAYS, SUBSCRIPTION_PLANS, TRIAL_DAYS, MANUAL_DIR, SUPPORT_URL
from mvm_bot.support_content import (
    SUPPORT_ROOT_BUTTONS,
    SUPPORT_ROOT_TEXT,
    SUPPORT_TOPICS,
    SUPPORT_VPN_DOWN_TEXT,
    VPN_ERROR_BUTTONS,
    VPN_ERROR_TOPICS,
)
from mvm_bot.firebase_client import get_tg_cached_attachment, set_tg_cached_attachment
from mvm_bot.main_menu import (
    format_subscription_end,
    has_active_subscription,
    main_menu_keyboard,
    send_main_menu,
)
from mvm_bot.freekassa import PAYMENT_CARD_RU, PAYMENT_SBERPAY, PAYMENT_SBP
from mvm_bot.freekassa import checkout_url as freekassa_checkout_url
from mvm_bot.heleket import invoice_checkout_url
from mvm_bot.platega import transaction_checkout_url as platega_checkout_url
from mvm_bot.yoomoney import PAYMENT_TYPE_CARD as YM_CARD
from mvm_bot.yoomoney import PAYMENT_TYPE_SBP as YM_SBP
from mvm_bot.yoomoney import checkout_url as yoomoney_checkout_url
from mvm_bot.datetime_utils import as_utc_datetime
from mvm_bot.user_service import (
    apply_referral_code_tg,
    apply_promo_code_tg,
    count_referrals,
    extend_subscription_with_tier,
    grant_purchase_referral_bonus_tg,
    record_payment_checkout_click,
    save_telegram_user,
    start_telegram_trial,
)
from mvm_bot.user_service.promo import check_promo_code_validity
from mvm_bot.remnawave_client import get_user_hwid_devices, delete_user_hwid_device



router = Router()


class ReferralStates(StatesGroup):
    waiting_for_code = State()


class PromoStates(StatesGroup):
    waiting_for_promo = State()


_PROMO_CANDIDATE_RE = re.compile(r"^[A-Z0-9_-]{4,32}$")


def _extract_promo_candidate(raw_text: str) -> tuple[str | None, bool]:
    text = raw_text.strip()
    if not text:
        return None, False

    lowered = text.lower()
    explicit_prefix = lowered.startswith("promo_") or lowered.startswith("promo ")
    if explicit_prefix:
        candidate = text[6:].strip().upper()
    else:
        candidate = text.upper()

    if not _PROMO_CANDIDATE_RE.fullmatch(candidate):
        return None, explicit_prefix
    return candidate, explicit_prefix


def _promo_multiplier(promo_activated: bool, promo_discount: object | None = None) -> float:
    if not promo_activated:
        return 1.0
    try:
        discount = float(promo_discount)
    except (TypeError, ValueError):
        discount = 0
    if 1 < discount <= 100:
        discount /= 100.0
    if not (0 < discount < 1):
        discount = 0
    return 1.0 - discount


def _plan_selection_keyboard(
    promo_activated: bool = False,
    promo_discount: object | None = None,
) -> InlineKeyboardMarkup:
    promo_multiplier = _promo_multiplier(promo_activated, promo_discount)
    rows: list[list[InlineKeyboardButton]] = []
    for plan_key in ["std_30", "std_90", "prem_30", "prem_90"]:
        plan = SUBSCRIPTION_PLANS[plan_key]
        if promo_activated:
            original_rub = plan['rub']
            discounted_rub = int(original_rub * promo_multiplier)
            struck_rub = "".join(char + "\u0336" for char in str(original_rub))
            text = f"{plan['emoji']} {plan['label']} — {struck_rub}₽/{discounted_rub}₽ — {plan['tier_label']}"
        else:
            text = f"{plan['emoji']} {plan['label']} — {plan['rub']} ₽ — {plan['tier_label']}"
        rows.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"buy:{plan_key}",
            ),
        ])

    if not promo_activated:
        rows.append([
            InlineKeyboardButton(
                text="🎟️ Ввести промокод",
                callback_data="promo:enter_code",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="« Назад",
            callback_data="menu:main",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _payment_method_keyboard(
    plan_key: str,
    promo_activated: bool = False,
    promo_discount: object | None = None,
) -> InlineKeyboardMarkup:
    plan = SUBSCRIPTION_PLANS[plan_key]
    rub = plan['rub']
    stars = plan['stars']
    promo_multiplier = _promo_multiplier(promo_activated, promo_discount)
    if promo_activated:
        rub = int(rub * promo_multiplier)
        stars = int(stars * promo_multiplier)
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


def _other_payment_method_keyboard(
    plan_key: str,
    promo_activated: bool = False,
    promo_discount: object | None = None,
) -> InlineKeyboardMarkup:
    plan = SUBSCRIPTION_PLANS[plan_key]
    rub = plan['rub']
    promo_multiplier = _promo_multiplier(promo_activated, promo_discount)
    if promo_activated:
        rub = int(rub * promo_multiplier)
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



@router.message(CommandStart())
async def start(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        await message.answer("Cannot identify Telegram user.")
        return

    referral_code = None
    if command.args and command.args.startswith("ref_"):
        referral_code = command.args[4:]

    _, data = await save_telegram_user(message.from_user, referral_code)

    reply_markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Профиль")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        "Добро пожаловать в MVM VPN! 🚀\n\nНажмите кнопку «Профиль» ниже для доступа к личному кабинету 👇",
        reply_markup=reply_markup,
    )
    await send_main_menu(message, data)


@router.message(F.text == "Профиль")
async def profile_command(message: Message) -> None:
    if message.from_user is None:
        await message.answer("Cannot identify Telegram user.")
        return

    _, data = await save_telegram_user(message.from_user)
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
            reply_markup=await main_menu_keyboard(callback.from_user.id, data),
        )


@router.callback_query(F.data == "menu:buy_subscription")
async def buy_subscription_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message and isinstance(callback.message, Message):
        _, data = await save_telegram_user(callback.from_user)
        promo_activated = data.get("promoActivated", False)
        promo_discount = data.get("promoDiscount")
        await callback.message.answer(
            "Доступные варианты:\n\n"
            "🤩 <b>Standart</b>:\n"
            "— 1 устройство;\n"
            "— базовые ускорители при ограничениях;\n"
            "— 6 серверов;\n\n"
            "💎 <b>Premium</b>:\n"
            "— 7 устройств;\n"
            "— дополнительные ускорители при ограничениях;\n"
            "— 22 сервера;",
            reply_markup=_plan_selection_keyboard(
                promo_activated=promo_activated,
                promo_discount=promo_discount,
            ),
            parse_mode=ParseMode.HTML,
        )


@router.callback_query(F.data.startswith("buy:"))
async def select_plan_callback(callback: CallbackQuery, bot: Bot) -> None:
    if callback.data is None or callback.from_user is None:
        await callback.answer("Ошибка.", show_alert=True)
        return

    _, data = await save_telegram_user(callback.from_user)
    promo_activated = data.get("promoActivated", False)
    promo_discount = data.get("promoDiscount")
    promo_multiplier = _promo_multiplier(promo_activated, promo_discount)

    parts = callback.data.split(":")
    if len(parts) == 2:
        _, plan_key = parts
        plan = SUBSCRIPTION_PLANS.get(plan_key)
        if plan is None:
            await callback.answer("Неизвестный план.", show_alert=True)
            return
        await callback.answer()
        text = f"{plan['label']} — выберите способ оплаты:"
        kb = _payment_method_keyboard(
            plan_key,
            promo_activated=promo_activated,
            promo_discount=promo_discount,
        )
        if callback.message and isinstance(callback.message, Message):
            try:
                await callback.message.edit_text(text, reply_markup=kb)
            except Exception:
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
        stars = plan["stars"]
        if promo_activated:
            stars = int(stars * promo_multiplier)
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"VPN подписка — {plan['label']}",
            description=f"Доступ к VPN на {plan['days']} дней.",
            payload=plan_key,
            currency="XTR",
            prices=[LabeledPrice(label=plan["label"], amount=stars)],
        )
        return

    if method in ("ym_card", "ym_sbp"):
        uid = callback.from_user.id
        receiver = yoomoney_receiver()
        if not receiver:
            await bot.send_message(
                chat_id=uid,
                text="Оплата через ЮMoney сейчас недоступна. Напишите в поддержку.",
            )
            return
        rub = plan.get("rub")
        if rub is None:
            await bot.send_message(
                chat_id=uid,
                text="Для этого плана оплата не настроена.",
            )
            return
        if promo_activated:
            rub = int(rub * promo_multiplier)
        if method == "ym_sbp":
            payment_type = YM_SBP
            method_label = "📲 СБП (QR)"
        else:
            payment_type = YM_CARD
            method_label = "💳 ЮMoney карта"
        try:
            ym = await yoomoney_checkout_url(
                receiver=receiver,
                provider="tg",
                user_id=uid,
                plan_key=plan_key,
                amount=float(rub),
                payment_type=payment_type,
                success_url=yoomoney_return_url(),
            )
            checkout = ym.url
        except Exception:
            logging.exception("YooMoney URL build failed")
            await bot.send_message(
                chat_id=uid,
                text="Не удалось создать ссылку на оплату. Попробуйте позже или напишите в поддержку.",
            )
            return

        try:
            await asyncio.to_thread(
                record_payment_checkout_click,
                service="yoomoney",
                provider="tg",
                external_user_id=str(uid),
                plan_key=plan_key,
                amount=float(rub),
                currency="RUB",
                pay_url=checkout,
                channel="telegram",
                correlation_id=ym.label,
                payment_method=method,
            )
        except Exception:
            logging.exception("Failed to log YooMoney checkout click")

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
        if promo_activated:
            rub = int(rub * promo_multiplier)
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
        if promo_activated:
            rub = int(rub * promo_multiplier)
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
        if promo_activated:
            crypto_usd = float(crypto_usd * promo_multiplier)
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
        "fk_sbp": (PAYMENT_SBP, "📲 СБП (FK)"),
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
        if promo_activated:
            rub = int(rub * promo_multiplier)
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



@router.callback_query(F.data.startswith("buy_other:"))
async def select_other_payment_callback(callback: CallbackQuery, bot: Bot) -> None:
    if callback.data is None or callback.from_user is None:
        await callback.answer("Ошибка.", show_alert=True)
        return

    _, data = await save_telegram_user(callback.from_user)
    promo_activated = data.get("promoActivated", False)
    promo_discount = data.get("promoDiscount")

    parts = callback.data.split(":")
    if len(parts) == 2:
        _, plan_key = parts
        plan = SUBSCRIPTION_PLANS.get(plan_key)
        if plan is None:
            await callback.answer("Неизвестный план.", show_alert=True)
            return
        await callback.answer()
        text = f"{plan['label']} — другие способы оплаты:"
        kb = _other_payment_method_keyboard(
            plan_key,
            promo_activated=promo_activated,
            promo_discount=promo_discount,
        )
        if callback.message and isinstance(callback.message, Message):
            try:
                await callback.message.edit_text(text, reply_markup=kb)
            except Exception:
                await callback.message.answer(text, reply_markup=kb)
        else:
            await bot.send_message(chat_id=callback.from_user.id, text=text, reply_markup=kb)
        return

    await callback.answer("Ошибка данных.", show_alert=True)


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

    _, data = await extend_subscription_with_tier(message.from_user, plan_key)

    try:
        await grant_purchase_referral_bonus_tg(message.from_user)
    except Exception:
        logging.exception("Failed to grant referral purchase bonus")

    end = as_utc_datetime(data.get("subscriptionEndsAt"))
    end_str = f"{end:%d.%m.%Y}" if end else ""
    tier_emoji = "💎" if plan.get("tier") == "premium" else "🤩"
    tier_label = plan.get("tier_label", "")
    await message.answer(
        f"✅ Оплата прошла успешно!\n\n"
        f"📅 Подписка активна до {end_str}\n"
        f"(+ {plan['days']} дней — {tier_emoji} {tier_label})",
        reply_markup=await main_menu_keyboard(message.from_user.id, data),
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
            reply_markup=_plan_selection_keyboard(
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

    candidate, explicit_prefix = _extract_promo_candidate(message.text)
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
            reply_markup=_plan_selection_keyboard(
                promo_activated=True,
                promo_discount=data.get("promoDiscount"),
            ),
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(f"❌ {text}")


def _devices_keyboard(devices: list) -> InlineKeyboardMarkup:
    rows = []
    for dev in devices:
        if isinstance(dev, dict):
            hwid = dev.get("hwid")
            model = dev.get("deviceModel") or dev.get("device_model") or dev.get("hwid") or "Device"
            if hwid:
                # Truncate device name to fit nicely on button
                btn_name = model[:20] + "..." if len(model) > 20 else model
                rows.append([
                    InlineKeyboardButton(
                        text=f"❌ Удалить {btn_name}",
                        callback_data=f"dev:del:{hwid}"
                    )
                ])
    rows.append([
        InlineKeyboardButton(
            text="« Назад",
            callback_data="menu:main"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "menu:devices")
async def view_devices_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer("Cannot identify Telegram user.", show_alert=True)
        return

    _, data = await save_telegram_user(callback.from_user)
    if not has_active_subscription(data):
        await callback.answer("❌ У вас нет активной подписки.", show_alert=True)
        return

    await callback.answer()
    tier = data.get("subscriptionTier")
    rw_uuid = data.get("remnawaveUuid")

    devices = []
    if rw_uuid:
        try:
            devices = await get_user_hwid_devices(rw_uuid)
        except Exception:
            logging.exception("Failed to fetch Remnawave devices for cabinet")

    devices_count = len(devices)
    limit = 7 if tier == "premium" else 1

    text = f"📱 <b>Мои устройства</b>\n\n"
    text += f"⚙️ Лимит: <b>{devices_count} / {limit}</b>\n\n"

    if not devices:
        text += "У вас нет подключенных устройств. Устройства подключаются автоматически при входе в приложение MVM VPN на вашем телефоне или компьютере."
    else:
        text += "Список ваших устройств:\n"
        for i, dev in enumerate(devices, 1):
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

                name = " ".join(parts) if parts else (dev.get("hwid") or "Unknown Device")
                text += f"{i}. {name}\n"
        text += "\nВыберите устройство для удаления 👇"

    kb = _devices_keyboard(devices)
    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            await callback.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith("dev:del:"))
async def delete_device_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None or not callback.data:
        await callback.answer("Ошибка.", show_alert=True)
        return

    hwid = callback.data[8:]
    _, data = await save_telegram_user(callback.from_user)
    rw_uuid = data.get("remnawaveUuid")
    if not rw_uuid:
        await callback.answer("❌ Пользователь Remnawave не найден", show_alert=True)
        return

    try:
        await delete_user_hwid_device(rw_uuid, hwid)
        await callback.answer("✅ Устройство успешно удалено", show_alert=True)
        devices = await get_user_hwid_devices(rw_uuid)
    except Exception:
        logging.exception("Failed to delete Remnawave device")
        await callback.answer("❌ Ошибка при удалении устройства", show_alert=True)
        return

    tier = data.get("subscriptionTier")
    devices_count = len(devices)
    limit = 7 if tier == "premium" else 1

    text = f"📱 <b>Мои устройства</b>\n\n"
    text += f"⚙️ Лимит: <b>{devices_count} / {limit}</b>\n\n"

    if not devices:
        text += "У вас нет подключенных устройств. Устройства подключаются автоматически при входе в приложение MVM VPN на вашем телефоне или компьютере."
    else:
        text += "Список ваших устройств:\n"
        for i, dev in enumerate(devices, 1):
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

                name = " ".join(parts) if parts else (dev.get("hwid") or "Unknown Device")
                text += f"{i}. {name}\n"
        text += "\nВыберите устройство для удаления 👇"

    kb = _devices_keyboard(devices)
    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            pass


def _support_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=topic.label, callback_data=topic.tg_callback)]
        for topic in SUPPORT_ROOT_BUTTONS
    ]
    rows.append([InlineKeyboardButton(text="Написать агенту поддержки", url=SUPPORT_URL)])
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _support_vpn_errors_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=topic.label, callback_data=topic.tg_callback)]
        for topic in VPN_ERROR_BUTTONS
    ]
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="menu:support")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _cleanup_support_media(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    media_ids = data.get("support_media_ids")
    if media_ids:
        for mid in media_ids:
            try:
                await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=mid)
            except Exception:
                pass
        await state.update_data(support_media_ids=None)


async def _send_support_answer(
    callback: CallbackQuery,
    state: FSMContext,
    text: str,
    photos: list[str],
    back_callback: str = "menu:support",
    back_label: str = "« К списку вопросов",
) -> None:
    await _cleanup_support_media(callback, state)
    try:
        await callback.message.delete()
    except Exception:
        pass

    bot = callback.bot
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
            disable_web_page_preview=True
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
            parse_mode=ParseMode.HTML
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
            disable_web_page_preview=True
        )
        media_ids.append(sent_text_msg.message_id)

    await state.update_data(support_media_ids=media_ids)


@router.callback_query(F.data == "menu:support")
async def support_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _cleanup_support_media(callback, state)
    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        SUPPORT_ROOT_TEXT,
        reply_markup=_support_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def _send_support_submenu(
    callback: CallbackQuery,
    state: FSMContext,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    await _cleanup_support_media(callback, state)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "support:not_working")
async def support_not_working_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _send_support_submenu(
        callback,
        state,
        SUPPORT_VPN_DOWN_TEXT,
        _support_vpn_errors_keyboard(),
    )


def _register_support_topic_handlers() -> None:
    for topic_key in ("key", "add_device", "remove_device", "pc_tv"):
        topic = SUPPORT_TOPICS[topic_key]

        async def handler(
            callback: CallbackQuery,
            state: FSMContext,
            *,
            _topic=topic,
        ) -> None:
            await callback.answer()
            await _send_support_answer(callback, state, _topic.text, _topic.photos)

        router.callback_query.register(handler, F.data == topic.tg_callback)

    for topic in VPN_ERROR_TOPICS.values():
        async def handler(
            callback: CallbackQuery,
            state: FSMContext,
            *,
            _topic=topic,
        ) -> None:
            await callback.answer()
            await _send_support_answer(
                callback,
                state,
                _topic.text,
                _topic.photos,
                back_callback="support:not_working",
                back_label="« К списку ошибок",
            )

        router.callback_query.register(handler, F.data == topic.tg_callback)


_register_support_topic_handlers()


@router.callback_query(F.data == "menu:main")
async def back_to_main_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        await callback.answer("Cannot identify Telegram user.")
        return
    await callback.answer()
    await _cleanup_support_media(callback, state)
    _, data = await save_telegram_user(callback.from_user)
    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.delete()
        except Exception:
            pass
    await send_main_menu(callback.message, data, user=callback.from_user)


@router.callback_query(F.data == "menu:how_to_connect")
async def how_to_connect_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message and isinstance(callback.message, Message):
        text = (
            "❓Как подключить\n\n"
            "Видео инструкция подключения на телефон👇\n"
            "https://vk.ru/clip-223445666_456239017\n\n"
            "Видео инструкция подключения к белым спискам👇\n"
            "https://vk.ru/clip-223445666_456239020\n\n"
            "Видео инструкция подключения на ПК👇\n"
            "https://vk.ru/clip-223445666_456239018"
        )
        await callback.message.answer(text)


@router.callback_query(F.data.startswith("survey:"))
async def survey_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer("Error.")
        return
        
    reason = callback.data.split(":")[1]
    
    from mvm_bot.user_service.helpers import telegram_uid
    from mvm_bot.firebase_client import init_firebase
    from datetime import datetime, timezone
    
    try:
        db = init_firebase()
        auth_uid = telegram_uid(callback.from_user.id)
        docs = (
            db.collection("users")
            .where("externalTg", "in", [auth_uid, str(callback.from_user.id)])
            .limit(1)
            .get()
        )
        if docs:
            docs[0].reference.update({
                "surveyAnswer": reason,
                "surveyAnsweredAt": datetime.now(timezone.utc)
            })
    except Exception:
        logging.exception("Failed to save survey response for Telegram user")
        
    await callback.answer()
    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.edit_text("❤️Спасибо за уделенное время. Вы помогли сделать наш сервис лучше.")
        except Exception:
            await callback.message.answer("❤️Спасибо за уделенное время. Вы помогли сделать наш сервис лучше.")

