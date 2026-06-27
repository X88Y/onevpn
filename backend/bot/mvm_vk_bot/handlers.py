from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from vkbottle import Keyboard, OpenLink, Text
from vkbottle.bot import Bot, Message as VkMessage, MessageEvent as VkMessageEvent
from vkbottle.tools import PhotoMessageUploader
from vkbottle_types.events import GroupEventType

from mvm_bot.constants import (
    MANUAL_DIR,
    REFERRAL_BONUS_DAYS,
    REFERRAL_PURCHASE_BONUS_DAYS,
    SUBSCRIPTION_PLANS,
    TRIAL_DAYS,
)
from mvm_bot.support_content import SUPPORT_TOPICS, VPN_ERROR_TOPICS
from mvm_bot.jwt_auth import sign_vk_auth_jwt
from mvm_bot.main_menu import format_subscription_end
from mvm_bot.user_service import (
    apply_referral_code_vk,
    apply_promo_code_vk,
    count_referrals,
    save_vk_user,
    start_vk_trial,
)
from mvm_bot.user_service.promo import check_promo_code_validity
from mvm_bot.firebase_client import get_vk_cached_attachment, init_firebase, set_vk_cached_attachment
from mvm_bot.devices_ui import device_display_name, device_limit_for_tier
from mvm_bot.promo_utils import extract_promo_candidate
from mvm_bot.remnawave_client import get_user_hwid_devices, delete_user_hwid_device
from mvm_bot.user_service.helpers import vk_uid
from mvm_vk_bot.handlers_payments import handle_pay_command
from mvm_vk_bot.handlers_start import handle_private_message
from mvm_vk_bot.menu import (
    has_active_subscription,
    main_menu_keyboard_json,
    other_checkout_keyboard_json,
    plan_selection_keyboard_json,
    rub_checkout_keyboard_json,
    send_main_menu,
    send_main_menu_from_event,
    devices_keyboard_json,
    send_support_menu,
    send_support_vpn_errors_menu,
    support_answer_keyboard_json,
)
from mvm_vk_bot.profile import fetch_vk_profile

_VK_SUPPORT_TOPIC_BY_CMD = {
    topic.vk_cmd: topic
    for topic in list(SUPPORT_TOPICS.values()) + list(VPN_ERROR_TOPICS.values())
    if topic.vk_cmd != "sup_not_work"
}


def _sub_manage_keyboard_vk() -> str:
    from vkbottle import Callback, Keyboard
    kb = Keyboard(inline=True)
    kb.add(Callback(label="✅ Включить автоплатеж", payload={"c": "sub_toggle_on"}))
    kb.row()
    kb.add(Callback(label="❌ Выключить автоплатеж", payload={"c": "sub_toggle_off"}))
    kb.row()
    kb.add(Callback(label="⏰ Настроить дни", payload={"c": "sub_set_days"}))
    kb.row()
    kb.add(Callback(label="💳 Удалить карту", payload={"c": "delete_card_confirm"}))
    kb.row()
    kb.add(Callback(label="« Назад", payload={"c": "buy"}))
    return kb.get_json()


def _renewal_days_keyboard_vk() -> str:
    from vkbottle import Callback, Keyboard
    kb = Keyboard(inline=True)
    kb.add(Callback(label="1 день", payload={"c": "sub_days", "d": 1}))
    kb.row()
    kb.add(Callback(label="3 дня", payload={"c": "sub_days", "d": 3}))
    kb.row()
    kb.add(Callback(label="14 дней", payload={"c": "sub_days", "d": 14}))
    kb.row()
    kb.add(Callback(label="« Назад", payload={"c": "sub_manage"}))
    return kb.get_json()


def register_handlers(bot: Bot) -> None:
    @bot.on.private_message()
    async def start(message: VkMessage) -> None:
        await handle_private_message(message)

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

    async def _send_vk_support_answer(
        event: VkMessageEvent,
        text: str,
        photos: list[str],
        back_cmd: str = "support",
    ) -> None:
        token = getattr(getattr(event.ctx_api, "token_generator", None), "token", None)
        attachments = []
        if token:
            for photo_filename in photos:
                cached = await get_vk_cached_attachment(token, [photo_filename])
                if cached:
                    attachments.append(cached)
                else:
                    try:
                        uploader = PhotoMessageUploader(event.ctx_api)
                        attachment = await uploader.upload(
                            file_source=str(MANUAL_DIR / photo_filename),
                            peer_id=event.peer_id,
                        )
                        attachments.append(attachment)
                        await set_vk_cached_attachment(token, [photo_filename], attachment)
                    except Exception:
                        logging.exception(f"Failed to upload photo {photo_filename} to VK")

        attachment_str = ",".join(attachments) if attachments else None
        kb = support_answer_keyboard_json(back_cmd=back_cmd)
        await event.send_message(message=text, attachment=attachment_str, keyboard=kb, dont_parse_links=True)

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
            _, data, activated = await start_vk_trial(profile, group_id=event.group_id)
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
                keyboard=await main_menu_keyboard_json(event.user_id, data),
            )
            return

        if cmd == "buy":
            _, data = await save_vk_user(profile, group_id=event.group_id)
            promo_activated = data.get("promoActivated", False)
            promo_discount = data.get("promoDiscount")
            await event.send_message(
                message=(
                    "Доступные варианты:\n\n"
                    "🤩 Standart:\n"
                    "— 1 устройство;\n"
                    "— базовые ускорители при ограничениях;\n"
                    "— 6 серверов;\n\n"
                    "💎 Premium:\n"
                    "— 7 устройств;\n"
                    "— дополнительные ускорители при ограничениях;\n"
                    "— 22 сервера;"
                ),
                keyboard=plan_selection_keyboard_json(
                    promo_activated=promo_activated,
                    promo_discount=promo_discount,
                    user_data=data,
                ),
            )
            return

        if cmd == "plan":
            plan_key_raw = payload.get("p")
            if not isinstance(plan_key_raw, str):
                return
            plan = SUBSCRIPTION_PLANS.get(plan_key_raw)
            if plan is None:
                return
            _, data = await save_vk_user(profile, group_id=event.group_id)
            promo_activated = data.get("promoActivated", False)
            promo_discount = data.get("promoDiscount")
            await event.send_message(
                message=f"{plan['label']} — выберите способ оплаты:",
                keyboard=rub_checkout_keyboard_json(
                    plan_key_raw,
                    promo_activated=promo_activated,
                    promo_discount=promo_discount,
                ),
            )
            return

        if cmd == "other_pay":
            plan_key_raw = payload.get("p")
            if not isinstance(plan_key_raw, str):
                return
            plan = SUBSCRIPTION_PLANS.get(plan_key_raw)
            if plan is None:
                return
            _, data = await save_vk_user(profile, group_id=event.group_id)
            promo_activated = data.get("promoActivated", False)
            promo_discount = data.get("promoDiscount")
            await event.send_message(
                message=f"{plan['label']} — другие способы оплаты:",
                keyboard=other_checkout_keyboard_json(
                    plan_key_raw,
                    promo_activated=promo_activated,
                    promo_discount=promo_discount,
                ),
            )
            return

        if cmd == "promo_enter":
            await event.send_message(
                message="🎟️ Чтобы активировать промокод, отправьте его в чат с приставкой promo_, например: promo_MVM40"
            )
            return

        if cmd == "delete_card_confirm":
            kb = Keyboard(inline=True)
            kb.add(Callback("✅ Да, удалить", payload={"c": "delete_card_yes"}))
            kb.row()
            kb.add(Callback("🚫 Не удалять", payload={"c": "delete_card_no"}))
            await event.send_message(
                message="🗑️ Вы уверены, что хотите удалить привязанную карту?",
                keyboard=kb.get_json(),
            )
            return

        if cmd == "delete_card_yes":
            db = init_firebase()
            auth_uid = vk_uid(profile.id)
            users_ref = db.collection("users")

            def perform_update():
                docs = users_ref.where("externalVk", "in", [auth_uid, str(profile.id)]).limit(1).get()
                if docs:
                    docs[0].reference.update({
                        "cardDeleted": True,
                        "subscriptionEndsAt": None,
                        "autoRenewalEnabled": False
                    })

            await asyncio.to_thread(perform_update)
            await _ack(event, "💳 Карта успешно удалена!")

            try:
                await event.ctx_api.messages.delete(message_ids=[event.message_id], delete_for_all=True)
            except Exception:
                pass
            return

        if cmd == "delete_card_no":
            await _ack(event)
            try:
                await event.ctx_api.messages.delete(message_ids=[event.message_id], delete_for_all=True)
            except Exception:
                pass
            return

        if cmd == "sub_manage":
            _, data = await save_vk_user(profile, group_id=event.group_id)
            sub_end = format_subscription_end(data)
            auto_pay = "✅ Включен" if data.get("autoRenewalEnabled") is True else "❌ Выключен"
            days_val = data.get("renewalDaysBefore", 3)
            days_map = {1: "1 день", 3: "3 дня", 14: "14 дней"}
            days_str = days_map.get(days_val, f"{days_val} дн.")

            status_text = (
                "📋 Управление подпиской\n\n"
                f"📅 Подписка: {sub_end}\n"
                f"💳 Автоплатеж: {auto_pay}\n"
                f"⏰ Списание за: {days_str} до окончания"
            )

            await event.send_message(
                message=status_text,
                keyboard=_sub_manage_keyboard_vk(),
            )
            return

        if cmd == "sub_set_days":
            await event.send_message(
                message="⏰ Выберите за сколько дней до окончания списывать средства:",
                keyboard=_renewal_days_keyboard_vk(),
            )
            return

        if cmd == "sub_days":
            days_val = payload.get("d")
            days_map = {1: "1 день", 3: "3 дня", 14: "14 дней"}
            label = days_map.get(days_val, str(days_val))
            if days_val is not None:
                db = init_firebase()
                auth_uid = vk_uid(profile.id)
                users_ref = db.collection("users")

                def save_vk_days():
                    docs = users_ref.where("externalVk", "in", [auth_uid, str(profile.id)]).limit(1).get()
                    if docs:
                        docs[0].reference.update({"renewalDaysBefore": int(days_val)})

                await asyncio.to_thread(save_vk_days)
            await _ack(event, f"✅ Установлено: списывать за {label} до окончания")

            _, data = await save_vk_user(profile, group_id=event.group_id)
            sub_end = format_subscription_end(data)
            auto_pay = "✅ Включен" if data.get("autoRenewalEnabled") is True else "❌ Выключен"
            days_str = days_map.get(days_val, f"{days_val} дн.") if days_val else "3 дня"
            status_text = (
                "📋 Управление подпиской\n\n"
                f"📅 Подписка: {sub_end}\n"
                f"💳 Автоплатеж: {auto_pay}\n"
                f"⏰ Списание за: {days_str} до окончания"
            )
            await event.send_message(
                message=status_text,
                keyboard=_sub_manage_keyboard_vk(),
            )
            return

        if cmd == "sub_toggle_on":
            db = init_firebase()
            auth_uid = vk_uid(profile.id)
            users_ref = db.collection("users")

            def check_and_save():
                docs = users_ref.where("externalVk", "in", [auth_uid, str(profile.id)]).limit(1).get()
                if docs:
                    user_data = docs[0].to_dict() or {}
                    if user_data.get("cardDeleted") is True:
                        return False
                    docs[0].reference.update({"autoRenewalEnabled": True})
                    return True
                return None

            result = await asyncio.to_thread(check_and_save)
            if result is False:
                await _ack(event, "❌ Невозможно включить автоплатеж: карта удалена.")
            elif result is True:
                await _ack(event, "✅ Подписка включена!")
                _, data = await save_vk_user(profile, group_id=event.group_id)
                sub_end = format_subscription_end(data)
                auto_pay = "✅ Включен"
                days_val = data.get("renewalDaysBefore", 3)
                days_map = {1: "1 день", 3: "3 дня", 14: "14 дней"}
                days_str = days_map.get(days_val, f"{days_val} дн.")
                status_text = (
                    "📋 Управление подпиской\n\n"
                    f"📅 Подписка: {sub_end}\n"
                    f"💳 Автоплатеж: {auto_pay}\n"
                    f"⏰ Списание за: {days_str} до окончания"
                )
                await event.send_message(
                    message=status_text,
                    keyboard=_sub_manage_keyboard_vk(),
                )
            else:
                await _ack(event, "❌ Пользователь не найден.")
            return

        if cmd == "sub_toggle_off":
            kb = Keyboard(inline=True)
            kb.add(Callback("✅ Да, выключить", payload={"c": "sub_toggle_off_yes"}))
            kb.row()
            kb.add(Callback("🚫 Отмена", payload={"c": "sub_toggle_off_no"}))
            await event.send_message(
                message="🗑️ Вы уверены, что хотите выключить автоплатеж?",
                keyboard=kb.get_json(),
            )
            return

        if cmd == "sub_toggle_off_yes":
            db = init_firebase()
            auth_uid = vk_uid(profile.id)
            users_ref = db.collection("users")

            def save_vk_toggle_off():
                docs = users_ref.where("externalVk", "in", [auth_uid, str(profile.id)]).limit(1).get()
                if docs:
                    docs[0].reference.update({"autoRenewalEnabled": False})

            await asyncio.to_thread(save_vk_toggle_off)
            await _ack(event, "❌ Подписка выключена!")

            try:
                await event.ctx_api.messages.delete(message_ids=[event.message_id], delete_for_all=True)
            except Exception:
                pass
            return

        if cmd == "sub_toggle_off_no":
            await _ack(event)
            try:
                await event.ctx_api.messages.delete(message_ids=[event.message_id], delete_for_all=True)
            except Exception:
                pass
            return

        if cmd == "pay":
            if await handle_pay_command(event, profile, payload):
                return

        if cmd == "invite":
            _, data = await save_vk_user(profile, group_id=event.group_id)
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
                    f"• Зарегистрировался — вы получите +{REFERRAL_BONUS_DAYS} дней\n"
                    f"• Совершил покупку — вы получите ещё +{REFERRAL_PURCHASE_BONUS_DAYS} дней\n\n"
                    f"Новый пользователь тоже получит +{REFERRAL_BONUS_DAYS} дней!"
                ),
            )
            return

        if cmd == "devices":
            _, data = await save_vk_user(profile, group_id=event.group_id)
            if not has_active_subscription(data):
                await event.send_message(message="❌ У вас нет активной подписки.")
                return
            tier = data.get("subscriptionTier")
            rw_uuid = data.get("remnawaveUuid")

            devices = []
            if rw_uuid:
                try:
                    devices = await get_user_hwid_devices(rw_uuid)
                except Exception:
                    logging.exception("Failed to fetch Remnawave devices for VK")

            devices_count = len(devices)
            limit = device_limit_for_tier(tier)

            text = f"📱 Мои устройства\n\n"
            text += f"⚙️ Лимит: {devices_count} / {limit}\n\n"

            if not devices:
                text += "У вас нет подключенных устройств. Устройства подключаются автоматически при входе в приложение MVM VPN на вашем телефоне или компьютере."
            else:
                text += "Список ваших устройств:\n"
                for i, dev in enumerate(devices, 1):
                    if isinstance(dev, dict):
                        name = device_display_name(dev)
                        text += f"{i}. {name}\n"
                text += "\nВыберите устройство для удаления 👇"

            kb = devices_keyboard_json(devices)
            await event.send_message(message=text, keyboard=kb)
            return

        if cmd == "del_dev":
            hwid = payload.get("id")
            if not isinstance(hwid, str):
                return
            _, data = await save_vk_user(profile, group_id=event.group_id)
            rw_uuid = data.get("remnawaveUuid")
            if not rw_uuid:
                await event.send_message(message="❌ Пользователь Remnawave не найден.")
                return

            try:
                await delete_user_hwid_device(rw_uuid, hwid)
                devices = await get_user_hwid_devices(rw_uuid)
            except Exception:
                logging.exception("Failed to delete Remnawave device for VK")
                await event.send_message(message="❌ Ошибка при удалении устройства.")
                return

            tier = data.get("subscriptionTier")
            devices_count = len(devices)
            limit = device_limit_for_tier(tier)

            text = f"✅ Устройство успешно удалено\n\n"
            text += f"📱 Мои устройства\n"
            text += f"⚙️ Лимит: {devices_count} / {limit}\n\n"

            if not devices:
                text += "У вас нет подключенных устройств."
            else:
                text += "Список ваших устройств:\n"
                for i, dev in enumerate(devices, 1):
                    if isinstance(dev, dict):
                        name = device_display_name(dev)
                        text += f"{i}. {name}\n"
                text += "\nВыберите устройство для удаления 👇"

            kb = devices_keyboard_json(devices)
            await event.send_message(message=text, keyboard=kb)
            return

        if cmd == "how_to_connect":
            text = (
                "❓Как подключить\n\n"
                "Видео инструкция подключения на телефон👇\n"
                "https://vk.ru/clip-223445666_456239027\n\n"
                "Видео инструкция подключения к белым спискам👇\n"
                "https://vk.ru/clip-223445666_456239020\n\n"
                "Видео инструкция подключения на ПК👇\n"
                "https://vk.ru/clip-223445666_456239018"
            )
            await event.send_message(message=text)
            return

        if cmd == "support":
            await send_support_menu(event)
            return

        support_topic = _VK_SUPPORT_TOPIC_BY_CMD.get(cmd)
        if support_topic is not None:
            back_cmd = "sup_not_work" if cmd.startswith("sup_err_") else "support"
            await _send_vk_support_answer(
                event,
                support_topic.text,
                support_topic.photos,
                back_cmd=back_cmd,
            )
            return

        if cmd == "sup_not_work":
            await send_support_vpn_errors_menu(event)
            return

        if cmd == "survey":
            reason = payload.get("r")
            try:
                db = init_firebase()
                auth_uid = vk_uid(profile.id)
                docs = db.collection("users").where("externalVk", "in", [auth_uid, str(profile.id)]).limit(1).get()
                if docs:
                    docs[0].reference.update({
                        "surveyAnswer": reason,
                        "surveyAnsweredAt": datetime.now(timezone.utc)
                    })
            except Exception:
                logging.exception("Failed to save survey response for VK user")
            await event.send_message(message="❤️Спасибо за уделенное время. Вы помогли сделать наш сервис лучше.")
            return

        if cmd == "main":
            _, data = await save_vk_user(profile, group_id=event.group_id)
            await send_main_menu_from_event(event, data)
            return
