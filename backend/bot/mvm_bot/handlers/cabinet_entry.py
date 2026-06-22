import logging
from datetime import datetime, timezone

from aiogram import F, Router  # type: ignore[import-not-found]
from aiogram.filters import CommandObject, CommandStart  # type: ignore[import-not-found]
from aiogram.fsm.context import FSMContext  # type: ignore[import-not-found]
from aiogram.types import (  # type: ignore[import-not-found]
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from mvm_bot.constants import TRIAL_DAYS
from mvm_bot.firebase_client import init_firebase
from mvm_bot.handlers.cabinet_shared import cleanup_support_media
from mvm_bot.main_menu import format_subscription_end, main_menu_keyboard, send_main_menu
from mvm_bot.user_service import save_telegram_user, start_telegram_trial
from mvm_bot.user_service.helpers import telegram_uid

router = Router()


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
        resize_keyboard=True,
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


@router.callback_query(F.data == "menu:main")
async def back_to_main_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None:
        await callback.answer("Cannot identify Telegram user.")
        return
    await callback.answer()
    await cleanup_support_media(callback, state)
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
            docs[0].reference.update(
                {
                    "surveyAnswer": reason,
                    "surveyAnsweredAt": datetime.now(timezone.utc),
                }
            )
    except Exception:
        logging.exception("Failed to save survey response for Telegram user")

    await callback.answer()
    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.edit_text("❤️Спасибо за уделенное время. Вы помогли сделать наш сервис лучше.")
        except Exception:
            await callback.message.answer("❤️Спасибо за уделенное время. Вы помогли сделать наш сервис лучше.")
