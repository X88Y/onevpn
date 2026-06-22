import asyncio
import logging
from datetime import datetime, timezone

from vkbottle import Callback, Keyboard, KeyboardButtonColor, OpenLink
from vkbottle.bot import Message, MessageEvent
from vkbottle.tools import PhotoMessageUploader

from mvm_bot.config import vk_menu_banner_path
from mvm_bot.constants import SUBSCRIPTION_PLANS, TRIAL_FIELDS, VK_SUPPORT_URL
from mvm_bot.support_content import (
    SUPPORT_ROOT_BUTTONS,
    SUPPORT_ROOT_TEXT,
    SUPPORT_VPN_DOWN_TEXT,
    VPN_ERROR_BUTTONS,
)
from mvm_bot.datetime_utils import as_utc_datetime
from mvm_bot.main_menu import main_menu_caption

_banner_attachments_cache = {}


def set_cached_banner(token: str, attachment: str) -> None:
    _banner_attachments_cache[token] = attachment


def get_cached_banner(token: str) -> str | None:
    return _banner_attachments_cache.get(token)


async def preupload_menu_banner(tokens: list[str]) -> None:
    banner = vk_menu_banner_path()
    if not banner or not tokens:
        return

    from vkbottle import API
    from vkbottle.tools import PhotoMessageUploader
    from mvm_bot.firebase_client import get_vk_cached_attachment, set_vk_cached_attachment

    for token in tokens:
        # Check Firestore cache first
        cached = await get_vk_cached_attachment(token, [banner.name])
        if cached:
            set_cached_banner(token, cached)
            logging.info(f"Loaded menu banner attachment ID from Firestore cache for token {token[:8]}: {cached}")
            continue

        api = API(token)
        uploader = PhotoMessageUploader(api)
        attempts = 5
        success = False
        for attempt in range(1, attempts + 1):
            try:
                logging.info(f"Pre-uploading menu banner for token {token[:8]} (attempt {attempt}/{attempts})...")
                attachment = await uploader.upload(file_source=str(banner))
                set_cached_banner(token, attachment)
                await set_vk_cached_attachment(token, [banner.name], attachment)
                logging.info(f"Successfully pre-uploaded banner for token {token[:8]} and saved to Firestore: {attachment}")
                success = True
                break
            except Exception as e:
                logging.error(f"Failed to pre-upload banner for token {token[:8]} (attempt {attempt}/{attempts}): {e}")
                if attempt < attempts:
                    await asyncio.sleep(3)
        if not success:
            logging.error(f"Failed to pre-upload banner for token {token[:8]} after all attempts.")


def has_active_subscription(data: dict) -> bool:
    end = as_utc_datetime(data.get("subscriptionEndsAt"))
    if end is None:
        return False
    return end > datetime.now(timezone.utc)


def _promo_multiplier(promo_activated: bool, promo_discount: object | None = None) -> float:
    if not promo_activated:
        return 1.0
    try:
        discount = float(promo_discount)
    except (TypeError, ValueError):
        discount = 0.4
    if 1 < discount <= 100:
        discount /= 100.0
    if not (0 < discount < 1):
        discount = 0.4
    return 1.0 - discount


async def main_menu_keyboard_json(vk_id: int, data: dict) -> str:
    is_active = has_active_subscription(data)
    kb = Keyboard(inline=True)
    
    sub_url = data.get("remnawaveSubscriptionUrl")
    if is_active and sub_url:
        kb.add(
            OpenLink(
                label="🔗 Подключить",
                link=sub_url,
            )
        )
        kb.row()

    if data.get(TRIAL_FIELDS["vk"]) is not True:
        kb.add(
            Callback(label="🎁 VPN бесплатно", payload={"c": "trial"}),
            color=KeyboardButtonColor.POSITIVE,
        )
    kb.add(
        Callback(label="💳 Купить", payload={"c": "buy"}),
        color=KeyboardButtonColor.POSITIVE if not is_active else None,
    )
    kb.row()

    if is_active:
        kb.add(Callback(label="📱 Мои устройства", payload={"c": "devices"}))
        kb.row()

    kb.add(Callback(label="👥 Пригласить друзей", payload={"c": "invite"}))
    kb.row()

    kb.add(Callback(label="❓ Как подключить", payload={"c": "how_to_connect"}))
    kb.add(Callback(label="💬 Поддержка", payload={"c": "support"}))
    return kb.get_json()


def plan_selection_keyboard_json(
    promo_activated: bool = False,
    promo_discount: object | None = None,
) -> str:
    promo_multiplier = _promo_multiplier(promo_activated, promo_discount)
    kb = Keyboard(inline=True)
    plan_keys = ["std_30", "std_90", "prem_30", "prem_90"]
    for i, plan_key in enumerate(plan_keys):
        plan = SUBSCRIPTION_PLANS[plan_key]
        if i > 0:
            kb.row()
        
        if promo_activated:
            original_rub = plan['rub']
            discounted_rub = int(original_rub * promo_multiplier)
            struck_rub = "".join(char + "\u0336" for char in str(original_rub))
            label = f"{plan['emoji']} {plan['label']} — {struck_rub}₽/{discounted_rub}₽ — {plan['tier_label']}"
        else:
            label = f"{plan['emoji']} {plan['label']} — {plan['rub']} ₽ — {plan['tier_label']}"
            
        kb.add(
            Callback(
                label=label,
                payload={"c": "plan", "p": plan_key},
            )
        )
    
    if not promo_activated:
        kb.row()
        kb.add(
            Callback(
                label="🎟️ Ввести промокод",
                payload={"c": "promo_enter"},
            )
        )
        
    kb.row()
    kb.add(
        Callback(
            label="« Назад",
            payload={"c": "main"},
        )
    )
    return kb.get_json()


def rub_checkout_keyboard_json(
    plan_key: str,
    promo_activated: bool = False,
    promo_discount: object | None = None,
) -> str:
    plan = SUBSCRIPTION_PLANS[plan_key]
    rub = plan['rub']
    promo_multiplier = _promo_multiplier(promo_activated, promo_discount)
    if promo_activated:
        rub = int(rub * promo_multiplier)
    kb = Keyboard(inline=True)
    kb.add(
        Callback(
            label=f"💳 ЮMoney карта — {rub} ₽",
            payload={"c": "pay", "p": plan_key, "m": "ym_card"},
        )
    )
    kb.row()
    kb.add(
        Callback(
            label=f"📲 СБП (QR) — {rub} ₽",
            payload={"c": "pay", "p": plan_key, "m": "ym_sbp"},
        ),
        color=KeyboardButtonColor.POSITIVE,
    )
    kb.row()
    kb.add(
        Callback(
            label=f"🔐 Crypto — {rub} ₽",
            payload={"c": "pay", "p": plan_key, "m": "rub"},
        )
    )
    kb.row()
    kb.add(
        Callback(
            label="🌐 Другие способы оплаты",
            payload={"c": "other_pay", "p": plan_key},
        )
    )
    return kb.get_json()


def other_checkout_keyboard_json(
    plan_key: str,
    promo_activated: bool = False,
    promo_discount: object | None = None,
) -> str:
    plan = SUBSCRIPTION_PLANS[plan_key]
    rub = plan['rub']
    promo_multiplier = _promo_multiplier(promo_activated, promo_discount)
    if promo_activated:
        rub = int(rub * promo_multiplier)
    kb = Keyboard(inline=True)
    kb.add(
        Callback(
            label=f"📲 СБП (FK) — {rub} ₽",
            payload={"c": "pay", "p": plan_key, "m": "fk_sbp"},
        )
    )
    kb.row()
    kb.add(
        Callback(
            label=f"💳 Карта РФ — {rub} ₽",
            payload={"c": "pay", "p": plan_key, "m": "fk_card"},
        )
    )
    kb.row()
    kb.add(
        Callback(
            label=f"💚 СберПэй — {rub} ₽",
            payload={"c": "pay", "p": plan_key, "m": "fk_sberpay"},
        )
    )
    kb.row()
    kb.add(
        Callback(
            label=f"🏦 СБП (Platega) — {rub} ₽",
            payload={"c": "pay", "p": plan_key, "m": "platega"},
        ),
        color=KeyboardButtonColor.POSITIVE,
    )
    kb.row()
    kb.add(
        Callback(
            label="« Назад",
            payload={"c": "plan", "p": plan_key},
        )
    )
    return kb.get_json()


async def send_main_menu(message: Message, data: dict) -> None:
    rw_uuid = data.get("remnawaveUuid")
    devices = []
    if rw_uuid:
        try:
            from mvm_bot.remnawave_client import get_user_hwid_devices
            devices = await get_user_hwid_devices(rw_uuid)
        except Exception:
            logging.exception("Failed to fetch Remnawave devices for VK main menu")

    caption = main_menu_caption(data, platform="vk", remnawave_devices=devices)
    keyboard = await main_menu_keyboard_json(message.from_id, data)
    banner = vk_menu_banner_path()
    if banner is not None:
        token = getattr(getattr(message.ctx_api, "token_generator", None), "token", None)
        cached_photo = get_cached_banner(token) if token else None

        # Check Firestore cache if not in memory
        if not cached_photo and token:
            from mvm_bot.firebase_client import get_vk_cached_attachment
            cached_photo = await get_vk_cached_attachment(token, [banner.name])
            if cached_photo:
                set_cached_banner(token, cached_photo)

        if cached_photo:
            try:
                await message.answer(message=caption, attachment=cached_photo, keyboard=keyboard, dont_parse_links=True)
                return
            except Exception:
                logging.exception("Failed to send main menu with cached banner")
        else:
            try:
                from mvm_bot.firebase_client import set_vk_cached_attachment
                uploader = PhotoMessageUploader(message.ctx_api)
                photo = await uploader.upload(
                    file_source=str(banner),
                    peer_id=message.peer_id,
                )
                if token:
                    set_cached_banner(token, photo)
                    await set_vk_cached_attachment(token, [banner.name], photo)
                await message.answer(message=caption, attachment=photo, keyboard=keyboard, dont_parse_links=True)
                return
            except Exception:
                logging.exception("VK banner upload failed, falling back to text-only menu")

    await message.answer(message=caption, keyboard=keyboard, dont_parse_links=True)


async def send_main_menu_from_event(event: MessageEvent, data: dict) -> None:
    rw_uuid = data.get("remnawaveUuid")
    devices = []
    if rw_uuid:
        try:
            from mvm_bot.remnawave_client import get_user_hwid_devices
            devices = await get_user_hwid_devices(rw_uuid)
        except Exception:
            logging.exception("Failed to fetch Remnawave devices for VK event main menu")

    caption = main_menu_caption(data, platform="vk", remnawave_devices=devices)
    keyboard = await main_menu_keyboard_json(event.user_id, data)
    banner = vk_menu_banner_path()
    if banner is not None:
        token = getattr(getattr(event.ctx_api, "token_generator", None), "token", None)
        cached_photo = get_cached_banner(token) if token else None
        if not cached_photo and token:
            from mvm_bot.firebase_client import get_vk_cached_attachment
            cached_photo = await get_vk_cached_attachment(token, [banner.name])
            if cached_photo:
                set_cached_banner(token, cached_photo)
        if cached_photo:
            try:
                await event.send_message(message=caption, attachment=cached_photo, keyboard=keyboard, dont_parse_links=True)
                return
            except Exception:
                logging.exception("Failed to send main menu with cached banner from event")
        else:
            try:
                from mvm_bot.firebase_client import set_vk_cached_attachment
                uploader = PhotoMessageUploader(event.ctx_api)
                photo = await uploader.upload(
                    file_source=str(banner),
                    peer_id=event.peer_id,
                )
                if token:
                    set_cached_banner(token, photo)
                    await set_vk_cached_attachment(token, [banner.name], photo)
                await event.send_message(message=caption, attachment=photo, keyboard=keyboard, dont_parse_links=True)
                return
            except Exception:
                logging.exception("VK banner upload failed from event, falling back to text-only menu")

    await event.send_message(message=caption, keyboard=keyboard, dont_parse_links=True)


def devices_keyboard_json(devices: list) -> str:
    kb = Keyboard(inline=True)
    valid_devices = []
    for d in devices:
        if isinstance(d, dict):
            hwid = d.get("hwid")
            if hwid:
                valid_devices.append(d)

    for i, d in enumerate(valid_devices):
        if i > 0 and i % 2 == 0:
            kb.row()
        model = d.get("deviceModel") or d.get("device_model") or d.get("hwid") or "Device"
        label = f"❌ {model}"
        if len(label) > 40:
            label = label[:37] + "..."
        kb.add(
            Callback(
                label=label,
                payload={"c": "del_dev", "id": d.get("hwid")}
            )
        )
    if valid_devices:
        kb.row()
    kb.add(
        Callback(
            label="« Назад",
            payload={"c": "main"}
        )
    )
    return kb.get_json()


VK_MAX_INLINE_BUTTONS = 5

SUPPORT_ROOT_FOLLOWUP_TEXT = (
    "Напишите агенту поддержки, если не нашли ответ 👇"
)
SUPPORT_VPN_ERRORS_FOLLOWUP_TEXT = "👇"


def _chunked_inline_keyboards(
    buttons: list[tuple],
) -> list[str]:
    """Build one or more inline keyboards, each with at most VK_MAX_INLINE_BUTTONS."""
    keyboards: list[str] = []
    for start in range(0, len(buttons), VK_MAX_INLINE_BUTTONS):
        chunk = buttons[start : start + VK_MAX_INLINE_BUTTONS]
        kb = Keyboard(inline=True)
        for i, btn in enumerate(chunk):
            if i > 0:
                kb.row()
            if len(btn) == 3 and btn[1] == "openlink":
                kb.add(OpenLink(label=btn[0], link=btn[2]))
            else:
                label, payload = btn[0], btn[1]
                kb.add(Callback(label=label, payload=payload))
        keyboards.append(kb.get_json())
    return keyboards


def support_keyboards_json() -> list[str]:
    buttons: list[tuple] = [
        (topic.label, {"c": topic.vk_cmd})
        for topic in SUPPORT_ROOT_BUTTONS
    ]
    buttons.extend([
        ("Написать агенту поддержки", "openlink", VK_SUPPORT_URL),
        ("« Назад", {"c": "main"}),
    ])
    return _chunked_inline_keyboards(buttons)


def support_vpn_errors_keyboards_json() -> list[str]:
    buttons: list[tuple] = [
        (topic.label, {"c": topic.vk_cmd})
        for topic in VPN_ERROR_BUTTONS
    ]
    buttons.append(("« Назад", {"c": "support"}))
    return _chunked_inline_keyboards(buttons)


async def _send_chunked_menu(
    event: MessageEvent,
    *,
    first_message: str,
    keyboards: list[str],
    followup_message: str,
) -> None:
    if not keyboards:
        return
    await event.send_message(message=first_message, keyboard=keyboards[0])
    for keyboard in keyboards[1:]:
        await event.send_message(message=followup_message, keyboard=keyboard)


async def send_support_menu(event: MessageEvent) -> None:
    await _send_chunked_menu(
        event,
        first_message=SUPPORT_ROOT_TEXT,
        keyboards=support_keyboards_json(),
        followup_message=SUPPORT_ROOT_FOLLOWUP_TEXT,
    )


async def send_support_vpn_errors_menu(event: MessageEvent) -> None:
    await _send_chunked_menu(
        event,
        first_message=SUPPORT_VPN_DOWN_TEXT,
        keyboards=support_vpn_errors_keyboards_json(),
        followup_message=SUPPORT_VPN_ERRORS_FOLLOWUP_TEXT,
    )


def support_answer_keyboard_json(back_cmd: str = "support") -> str:
    kb = Keyboard(inline=True)
    if back_cmd == "sup_not_work":
        back_label = "« К списку ошибок"
    else:
        back_label = "« К вопросам"
    kb.add(Callback(label=back_label, payload={"c": back_cmd}))
    kb.add(Callback(label="« В меню", payload={"c": "main"}))
    kb.row()
    kb.add(OpenLink(label="Написать агенту поддержки", link=VK_SUPPORT_URL))
    return kb.get_json()
