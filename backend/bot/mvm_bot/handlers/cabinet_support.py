from aiogram import F, Router  # type: ignore[import-not-found]
from aiogram.enums import ParseMode  # type: ignore[import-not-found]
from aiogram.fsm.context import FSMContext  # type: ignore[import-not-found]
from aiogram.types import CallbackQuery  # type: ignore[import-not-found]

from mvm_bot.handlers.cabinet_shared import (
    cleanup_support_media,
    send_support_answer,
    send_support_submenu,
    support_keyboard,
    support_vpn_errors_keyboard,
)
from mvm_bot.support_content import (
    SUPPORT_ROOT_TEXT,
    SUPPORT_TOPICS,
    SUPPORT_VPN_DOWN_TEXT,
    VPN_ERROR_TOPICS,
)

router = Router()


@router.callback_query(F.data == "menu:support")
async def support_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await cleanup_support_media(callback, state)
    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        SUPPORT_ROOT_TEXT,
        reply_markup=support_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "support:not_working")
async def support_not_working_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await send_support_submenu(
        callback,
        state,
        SUPPORT_VPN_DOWN_TEXT,
        support_vpn_errors_keyboard(),
    )


def register_support_topic_handlers() -> None:
    for topic_key in ("key", "add_device", "remove_device", "pc_tv"):
        topic = SUPPORT_TOPICS[topic_key]

        async def handler(
            callback: CallbackQuery,
            state: FSMContext,
            *,
            _topic=topic,
        ) -> None:
            await callback.answer()
            await send_support_answer(callback, state, _topic.text, _topic.photos)

        router.callback_query.register(handler, F.data == topic.tg_callback)

    for topic in VPN_ERROR_TOPICS.values():
        async def handler(
            callback: CallbackQuery,
            state: FSMContext,
            *,
            _topic=topic,
        ) -> None:
            await callback.answer()
            await send_support_answer(
                callback,
                state,
                _topic.text,
                _topic.photos,
                back_callback="support:not_working",
                back_label="« К списку ошибок",
            )

        router.callback_query.register(handler, F.data == topic.tg_callback)


register_support_topic_handlers()
