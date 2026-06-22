import asyncio
import logging

from aiogram import Bot, F, Router  # type: ignore[import-not-found]
from aiogram.enums import ParseMode  # type: ignore[import-not-found]
from aiogram.types import (  # type: ignore[import-not-found]
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from mvm_bot.handlers.cabinet_shared import (
    other_payment_method_keyboard,
    payment_method_keyboard,
    plan_selection_keyboard,
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
from mvm_bot.constants import CONNECT_REDIRECT_ORIGIN, SUBSCRIPTION_PLANS
from mvm_bot.datetime_utils import as_utc_datetime
from mvm_bot.freekassa import PAYMENT_CARD_RU, PAYMENT_SBERPAY, PAYMENT_SBP
from mvm_bot.freekassa import checkout_url as freekassa_checkout_url
from mvm_bot.heleket import invoice_checkout_url
from mvm_bot.main_menu import main_menu_keyboard
from mvm_bot.platega import transaction_checkout_url as platega_checkout_url
from mvm_bot.promo_utils import promo_multiplier
from mvm_bot.user_service import (
    extend_subscription_with_tier,
    grant_purchase_referral_bonus_tg,
    record_payment_checkout_click,
    save_telegram_user,
)
from mvm_bot.yoomoney import PAYMENT_TYPE_CARD as YM_CARD
from mvm_bot.yoomoney import PAYMENT_TYPE_SBP as YM_SBP
from mvm_bot.yoomoney import checkout_url as yoomoney_checkout_url

router = Router()


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
            reply_markup=plan_selection_keyboard(
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
    promo_factor = promo_multiplier(
        promo_activated,
        promo_discount,
        default_discount=0.0,
    )

    parts = callback.data.split(":")
    if len(parts) == 2:
        _, plan_key = parts
        plan = SUBSCRIPTION_PLANS.get(plan_key)
        if plan is None:
            await callback.answer("Неизвестный план.", show_alert=True)
            return
        await callback.answer()
        text = f"{plan['label']} — выберите способ оплаты:"
        kb = payment_method_keyboard(
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
            stars = int(stars * promo_factor)
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
            rub = int(rub * promo_factor)
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
                inline_keyboard=[[InlineKeyboardButton(text="Оплатить", url=checkout)]]
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
            rub = int(rub * promo_factor)
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
            logging.exception("Failed to log Heleket checkout click")

        await bot.send_message(
            chat_id=uid,
            text=(
                f"🔐 Crypto — {plan['label']} ({float(rub):.0f} ₽)\n\n"
                "После оплаты подписка продлится автоматически (обычно несколько минут).\n\n"
                f"Ссылка: {checkout}"
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Оплатить", url=checkout)]]
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
            await bot.send_message(chat_id=uid, text="Для этого плана оплата не настроена.")
            return
        if promo_activated:
            rub = int(rub * promo_factor)
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
                inline_keyboard=[[InlineKeyboardButton(text="Оплатить", url=checkout)]]
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
                    "Crypto-оплата сейчас недоступна. Напишите в поддержку: ссылка на оплату не сформировалась."
                ),
            )
            return
        crypto_usd = plan.get("crypto_usd")
        if crypto_usd is None:
            await bot.send_message(
                chat_id=uid,
                text="Для этого плана crypto-оплата не настроена.",
            )
            return
        if promo_activated:
            crypto_usd = float(crypto_usd * promo_factor)
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
            logging.exception("Heleket crypto invoice failed")
            await bot.send_message(
                chat_id=uid,
                text=(
                    "Не удалось создать crypto-ссылку на оплату. Попробуйте позже или напишите в поддержку."
                ),
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
            logging.exception("Failed to log Heleket crypto checkout click")

        await bot.send_message(
            chat_id=uid,
            text=(
                f"🔐 Crypto — {plan['label']} ({float(crypto_usd):.2f} USD)\n\n"
                "После оплаты подписка продлится автоматически (обычно несколько минут).\n\n"
                f"Ссылка: {checkout}"
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Оплатить", url=checkout)]]
            ),
        )
        return

    fk_methods = {
        "fk_sbp": (PAYMENT_SBP, "📲 СБП (FK)"),
        "fk_card": (PAYMENT_CARD_RU, "💳 Банк. карта РФ"),
        "fk_sberpay": (PAYMENT_SBERPAY, "💚 СберПэй"),
    }
    if method in fk_methods:
        uid = callback.from_user.id
        shop_id = freekassa_shop_id()
        api_key = freekassa_api_key()
        return_url = freekassa_return_url()
        if not shop_id or not api_key:
            await bot.send_message(
                chat_id=uid,
                text="Оплата через FreeKassa сейчас недоступна. Напишите в поддержку.",
            )
            return
        rub = plan.get("rub")
        if rub is None:
            await bot.send_message(chat_id=uid, text="Для этого плана оплата не настроена.")
            return
        if promo_activated:
            rub = int(rub * promo_factor)
        payment_system, method_label = fk_methods[method]
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
                success_url=return_url,
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
                inline_keyboard=[[InlineKeyboardButton(text="Оплатить", url=checkout)]]
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
        kb = other_payment_method_keyboard(
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
