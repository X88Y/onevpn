import asyncio
import logging

from vkbottle import Keyboard, OpenLink

from mvm_bot.config import (
    freekassa_api_key,
    freekassa_ip,
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
from mvm_bot.freekassa import PAYMENT_CARD_RU, PAYMENT_SBERPAY, PAYMENT_SBP
from mvm_bot.freekassa import checkout_url as freekassa_checkout_url
from mvm_bot.heleket import invoice_checkout_url
from mvm_bot.platega import transaction_checkout_url as platega_checkout_url
from mvm_bot.promo_utils import promo_multiplier
from mvm_bot.user_service import record_payment_checkout_click, save_vk_user
from mvm_bot.yoomoney import PAYMENT_TYPE_CARD as YM_CARD
from mvm_bot.yoomoney import PAYMENT_TYPE_SBP as YM_SBP
from mvm_bot.yoomoney import checkout_url as yoomoney_checkout_url


async def handle_pay_command(event, profile, payload: dict) -> bool:
    method = payload.get("m")
    plan_key_raw = payload.get("p")
    if not isinstance(plan_key_raw, str):
        return True
    plan = SUBSCRIPTION_PLANS.get(plan_key_raw)
    if plan is None:
        return True

    uid = event.user_id
    _, data = await save_vk_user(profile, group_id=event.group_id)
    promo_activated = data.get("promoActivated", False)
    promo_discount = data.get("promoDiscount")
    promo_factor = promo_multiplier(
        promo_activated,
        promo_discount,
        default_discount=0.4,
    )

    rub = plan.get("rub")
    if rub is None:
        await event.send_message(message="Для этого плана оплата не настроена.")
        return True
    if promo_activated:
        rub = int(rub * promo_factor)

    if method in ("ym_card", "ym_sbp"):
        receiver = yoomoney_receiver()
        if not receiver:
            await event.send_message(
                message="Оплата через ЮMoney сейчас недоступна. Напишите в поддержку."
            )
            return True
        if method == "ym_sbp":
            payment_type = YM_SBP
            method_label = "📲 СБП (QR)"
        else:
            payment_type = YM_CARD
            method_label = "💳 ЮMoney карта"
        try:
            ym = await yoomoney_checkout_url(
                receiver=receiver,
                provider="vk",
                user_id=uid,
                plan_key=plan_key_raw,
                amount=float(rub),
                payment_type=payment_type,
                success_url=yoomoney_return_url(),
            )
            checkout = ym.url
        except Exception:
            logging.exception("YooMoney URL build failed (VK)")
            await event.send_message(
                message=(
                    "Не удалось создать ссылку на оплату. "
                    "Попробуйте позже или напишите в поддержку."
                ),
            )
            return True

        try:
            await asyncio.to_thread(
                record_payment_checkout_click,
                service="yoomoney",
                provider="vk",
                external_user_id=str(uid),
                plan_key=plan_key_raw,
                amount=float(rub),
                currency="RUB",
                pay_url=checkout,
                channel="vk",
                correlation_id=ym.label,
                payment_method=method,
            )
        except Exception:
            logging.exception("Failed to log YooMoney checkout click (VK)")
        pay_kb = Keyboard(inline=True)
        pay_kb.add(OpenLink(label="Оплатить", link=checkout))
        await event.send_message(
            message=(
                f"{method_label} — {plan['label']} ({float(rub):.0f} ₽)\n\n"
                "После оплаты подписка продлится автоматически "
                "(обычно несколько минут).\n\n"
                f"Ссылка: {checkout}"
            ),
            keyboard=pay_kb.get_json(),
            dont_parse_links=True,
        )
        return True

    if method == "platega":
        merchant_id = platega_merchant_id()
        secret = platega_secret()
        if not merchant_id or not secret:
            await event.send_message(
                message=(
                    "Оплата картой сейчас недоступна. Напишите в поддержку."
                ),
            )
            return True
        try:
            pg = await platega_checkout_url(
                merchant_id=merchant_id,
                secret=secret,
                provider="vk",
                user_id=uid,
                plan_key=plan_key_raw,
                amount=float(rub),
                currency="RUB",
                description=f"VPN {plan['label']}",
                return_url=platega_return_url(),
                failed_url=platega_failed_url(),
            )
            checkout = pg.url
        except Exception:
            logging.exception("Platega transaction failed (VK)")
            await event.send_message(
                message=(
                    "Не удалось создать ссылку на оплату. "
                    "Попробуйте позже или напишите в поддержку."
                ),
            )
            return True

        try:
            await asyncio.to_thread(
                record_payment_checkout_click,
                service="platega",
                provider="vk",
                external_user_id=str(uid),
                plan_key=plan_key_raw,
                amount=float(rub),
                currency="RUB",
                pay_url=checkout,
                channel="vk",
                correlation_id=pg.payload,
                payment_method="platega",
            )
        except Exception:
            logging.exception("Failed to log Platega checkout click (VK)")
        pay_kb = Keyboard(inline=True)
        pay_kb.add(OpenLink(label="Оплатить", link=checkout))
        await event.send_message(
            message=(
                f"🏦 Оплата картой — {plan['label']} ({float(rub):.0f} ₽)\n\n"
                "После оплаты подписка продлится автоматически "
                "(обычно несколько минут).\n\n"
                f"Ссылка: {checkout}"
            ),
            keyboard=pay_kb.get_json(),
            dont_parse_links=True,
        )
        return True

    if method == "rub":
        merchant_uuid = heleket_merchant_uuid()
        api_key = heleket_payment_api_key()
        ipn_url = heleket_callback_url()
        if not merchant_uuid or not api_key or not ipn_url:
            await event.send_message(
                message=(
                    "Оплата сейчас недоступна. Напишите в поддержку: "
                    "ссылка на оплату не сформировалась."
                ),
            )
            return True
        try:
            inv = await invoice_checkout_url(
                merchant_uuid=merchant_uuid,
                api_key=api_key,
                ipn_callback_url=ipn_url,
                payer_user_id=uid,
                payer_provider="vk",
                plan_key=plan_key_raw,
                price_amount=float(rub),
                price_currency="rub",
                success_url=CONNECT_REDIRECT_ORIGIN,
            )
            checkout = inv.url
        except Exception:
            logging.exception("Heleket invoice failed (VK)")
            await event.send_message(
                message=(
                    "Не удалось создать ссылку на оплату. "
                    "Попробуйте позже или напишите в поддержку."
                ),
            )
            return True

        try:
            await asyncio.to_thread(
                record_payment_checkout_click,
                service="heleket",
                provider="vk",
                external_user_id=str(uid),
                plan_key=plan_key_raw,
                amount=float(rub),
                currency="RUB",
                pay_url=checkout,
                channel="vk",
                correlation_id=inv.order_id,
                payment_method="rub",
            )
        except Exception:
            logging.exception("Failed to log Heleket checkout click (VK)")
        pay_kb = Keyboard(inline=True)
        pay_kb.add(OpenLink(label="Оплатить", link=checkout))
        await event.send_message(
            message=(
                f"🔐 Crypto — {plan['label']} ({float(rub):.0f} ₽)\n\n"
                "После оплаты подписка продлится автоматически "
                "(обычно несколько минут).\n\n"
                f"Ссылка: {checkout}"
            ),
            keyboard=pay_kb.get_json(),
            dont_parse_links=True,
        )
        return True

    fk_methods = {
        "fk_sbp": (PAYMENT_SBP, "📲 СБП (FK)"),
        "fk_card": (PAYMENT_CARD_RU, "💳 Банк. карта РФ"),
        "fk_sberpay": (PAYMENT_SBERPAY, "💚 СберПэй"),
    }
    if method in fk_methods:
        shop_id = freekassa_shop_id()
        api_key = freekassa_api_key()
        if not shop_id or not api_key:
            await event.send_message(
                message="Оплата через FreeKassa сейчас недоступна. Напишите в поддержку."
            )
            return True
        payment_system, method_label = fk_methods[method]
        try:
            fk = await freekassa_checkout_url(
                shop_id=shop_id,
                api_key=api_key,
                provider="vk",
                user_id=uid,
                plan_key=plan_key_raw,
                payment_system=payment_system,
                email=f"{uid}@vk.com",
                ip=freekassa_ip(),
                amount=float(rub),
            )
            checkout = fk.url
        except Exception:
            logging.exception("FreeKassa order creation failed (VK)")
            await event.send_message(
                message="Не удалось создать ссылку на оплату. Попробуйте позже или напишите в поддержку."
            )
            return True

        try:
            await asyncio.to_thread(
                record_payment_checkout_click,
                service="freekassa",
                provider="vk",
                external_user_id=str(uid),
                plan_key=plan_key_raw,
                amount=float(rub),
                currency="RUB",
                pay_url=checkout,
                channel="vk",
                correlation_id=fk.payment_id,
                payment_method=method,
                payment_system=payment_system,
            )
        except Exception:
            logging.exception("Failed to log FreeKassa checkout click (VK)")

        pay_kb = Keyboard(inline=True)
        pay_kb.add(OpenLink(label="Оплатить", link=checkout))
        await event.send_message(
            message=(
                f"{method_label} — {plan['label']} ({float(rub):.0f} ₽)\n\n"
                "После оплаты подписка продлится автоматически (обычно несколько минут).\n\n"
                f"Ссылка: {checkout}"
            ),
            keyboard=pay_kb.get_json(),
            dont_parse_links=True,
        )
        return True

    return False
