from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from vkbottle import Keyboard, OpenLink
from vkbottle_types.events import GroupEventType

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
)
from mvm_bot.constants import CONNECT_REDIRECT_ORIGIN, REFERRAL_BONUS_DAYS, SUBSCRIPTION_PLANS, TRIAL_DAYS
from mvm_bot.jwt_auth import sign_vk_auth_jwt
from mvm_bot.main_menu import format_subscription_end
from mvm_bot.freekassa import PAYMENT_CARD_RU, PAYMENT_SBERPAY, PAYMENT_SBP
from mvm_bot.freekassa import checkout_url as freekassa_checkout_url
from mvm_bot.heleket import invoice_checkout_url
from mvm_bot.platega import transaction_checkout_url as platega_checkout_url
from mvm_bot.user_service import (
    apply_referral_code_vk,
    count_referrals,
    record_payment_checkout_click,
    save_vk_user,
    start_vk_trial,
)
from mvm_vk_bot.menu import (
    main_menu_keyboard_json,
    plan_selection_keyboard_json,
    rub_checkout_keyboard_json,
    send_main_menu,
)
from mvm_vk_bot.profile import fetch_vk_profile

if TYPE_CHECKING:
    from vkbottle.bot import Bot, Message, MessageEvent


def register_handlers(bot: Bot) -> None:
    from vkbottle.bot import Message as VkMessage
    from vkbottle.bot import MessageEvent as VkMessageEvent

    @bot.on.private_message()
    async def start(message: VkMessage) -> None:
        text = (message.text or "").strip()
        profile = await fetch_vk_profile(message.ctx_api, message.from_id)

        if text.startswith("ref_"):
            code = text[4:]
            _, data = await save_vk_user(profile)
            success, msg = await apply_referral_code_vk(profile, code)
            await message.answer(message=f"{'✅' if success else '❌'} {msg}")
            await send_main_menu(message, data)
            return

        _, data = await save_vk_user(profile)
        await send_main_menu(message, data)

    async def _ack(event: VkMessageEvent, snackbar_text: str | None = None) -> None:
        """Acknowledge a VK button event. Errors are swallowed — the token
        may already be expired or consumed (double-tap, retry, etc.)."""
        try:
            if snackbar_text:
                await event.show_snackbar(snackbar_text)
            else:
                await event.send_empty_answer()
        except Exception:
            logging.debug("VK event answer failed (token expired or already used)")

    @bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=VkMessageEvent)
    async def on_callback(event: VkMessageEvent) -> None:
        payload = event.payload
        if not isinstance(payload, dict):
            await _ack(event)
            return

        cmd = payload.get("c")

        # Acknowledge the event BEFORE any I/O so the token never times out.
        # Exception: "trial" uses the snackbar AS its acknowledgement, so we
        # defer it until after we know the outcome.
        if cmd != "trial":
            await _ack(event)

        profile = await fetch_vk_profile(event.ctx_api, event.user_id)

        if cmd == "trial":
            _, data, activated = await start_vk_trial(profile)
            if activated:
                providers = ", ".join(activated)
                days = TRIAL_DAYS * len(activated)
                await _ack(event, f"Пробный период активирован: +{days} дн. ({providers})")
                confirm = (
                    "✅ Подписка активирована\n\n"
                    f"📅 {format_subscription_end(data)}\n\n"
                    "Приятного пользования VPN! 🚀"
                )
            else:
                await _ack(event, "Бесплатный период уже был активирован ранее.")
                confirm = (
                    f"📅 Подписка: {format_subscription_end(data)}\n\n"
                    "Меню действий ниже 👇"
                )
            await event.send_message(
                message=confirm,
                keyboard=main_menu_keyboard_json(event.user_id, data),
            )
            return

        if cmd == "buy":
            await event.send_message(
                message="Доступные варианты:",
                keyboard=plan_selection_keyboard_json(),
            )
            return

        if cmd == "plan":
            plan_key_raw = payload.get("p")
            if not isinstance(plan_key_raw, str):
                return
            plan = SUBSCRIPTION_PLANS.get(plan_key_raw)
            if plan is None:
                return
            await event.send_message(
                message=f"{plan['label']} — выберите способ оплаты:",
                keyboard=rub_checkout_keyboard_json(plan_key_raw),
            )
            return

        if cmd == "pay":
            method = payload.get("m")
            plan_key_raw = payload.get("p")
            if not isinstance(plan_key_raw, str):
                return
            plan = SUBSCRIPTION_PLANS.get(plan_key_raw)
            if plan is None:
                return

            uid = event.user_id
            rub = plan.get("rub")
            if rub is None:
                await event.send_message(message="Для этого плана оплата не настроена.")
                return

            if method == "platega":
                merchant_id = platega_merchant_id()
                secret = platega_secret()
                if not merchant_id or not secret:
                    await event.send_message(
                        message=(
                            "Оплата картой сейчас недоступна. Напишите в поддержку."
                        ),
                    )
                    return
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
                    return

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
                )
                return

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
                    return
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
                    return

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
                )
                return

            _FK_METHODS = {
                "fk_sbp": (PAYMENT_SBP, "📲 СБП (QR)"),
                "fk_card": (PAYMENT_CARD_RU, "💳 Банк. карта РФ"),
                "fk_sberpay": (PAYMENT_SBERPAY, "💚 СберПэй"),
            }
            if method in _FK_METHODS:
                shop_id = freekassa_shop_id()
                api_key = freekassa_api_key()
                if not shop_id or not api_key:
                    await event.send_message(
                        message="Оплата через FreeKassa сейчас недоступна. Напишите в поддержку."
                    )
                    return
                payment_system, method_label = _FK_METHODS[method]
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
                    return

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
                )
                return

        if cmd == "invite":
            _, data = await save_vk_user(profile)
            referral_code = data.get("referralCode")
            if not referral_code:
                await event.send_message(message="Не удалось получить реферальный код. Попробуйте позже.")
                return
            invited_count = await count_referrals(referral_code)
            await event.send_message(
                message=(
                    f"👥 Пригласите друзей и получайте бонусы!\n\n"
                    f"📊 Приглашено друзей: {invited_count}\n\n"
                    f"📱 Ваш реферальный код: ref_{referral_code}\n\n"
                    f"Попросите друга написать этот код боту при первом сообщении.\n\n"
                    f"🎁 За каждого приглашённого:\n"
                    f"• Зарегистрировался — вы получите +{REFERRAL_BONUS_DAYS} дня\n\n"
                    f"Новый пользователь тоже получит +{REFERRAL_BONUS_DAYS} дня!"
                ),
            )
            return
