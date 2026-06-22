import logging

from aiogram import F, Router  # type: ignore[import-not-found]
from aiogram.enums import ParseMode  # type: ignore[import-not-found]
from aiogram.types import CallbackQuery, Message  # type: ignore[import-not-found]

from mvm_bot.devices_ui import device_display_name, device_limit_for_tier
from mvm_bot.handlers.cabinet_shared import devices_keyboard
from mvm_bot.main_menu import has_active_subscription
from mvm_bot.remnawave_client import delete_user_hwid_device, get_user_hwid_devices
from mvm_bot.user_service import save_telegram_user

router = Router()


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
    limit = device_limit_for_tier(tier)

    text = "📱 <b>Мои устройства</b>\n\n"
    text += f"⚙️ Лимит: <b>{devices_count} / {limit}</b>\n\n"

    if not devices:
        text += "У вас нет подключенных устройств. Устройства подключаются автоматически при входе в приложение MVM VPN на вашем телефоне или компьютере."
    else:
        text += "Список ваших устройств:\n"
        for i, dev in enumerate(devices, 1):
            if isinstance(dev, dict):
                name = device_display_name(dev)
                text += f"{i}. {name}\n"
        text += "\nВыберите устройство для удаления 👇"

    kb = devices_keyboard(devices)
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
    limit = device_limit_for_tier(tier)

    text = "📱 <b>Мои устройства</b>\n\n"
    text += f"⚙️ Лимит: <b>{devices_count} / {limit}</b>\n\n"

    if not devices:
        text += "У вас нет подключенных устройств. Устройства подключаются автоматически при входе в приложение MVM VPN на вашем телефоне или компьютере."
    else:
        text += "Список ваших устройств:\n"
        for i, dev in enumerate(devices, 1):
            if isinstance(dev, dict):
                name = device_display_name(dev)
                text += f"{i}. {name}\n"
        text += "\nВыберите устройство для удаления 👇"

    kb = devices_keyboard(devices)
    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            pass
