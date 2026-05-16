import asyncio
import logging

from aiogram import Bot, Dispatcher  # type: ignore[import-not-found]
from aiogram.fsm.storage.memory import MemoryStorage  # type: ignore[import-not-found]
from aiogram.types import BotCommand  # type: ignore[import-not-found]
from dotenv import load_dotenv  # type: ignore[import-not-found]

from mvm_bot.config import bot_token
from mvm_bot.constants import BOT_DIR
from mvm_bot.expiry_notifier import run_expiry_notifier_loop
from mvm_bot.handlers import router


async def main() -> None:
    load_dotenv(BOT_DIR / ".env")
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=bot_token())
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Open personal cabinet"),
        ]
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)

    notifier_task = asyncio.create_task(run_expiry_notifier_loop())

    try:
        await dispatcher.start_polling(bot)
    finally:
        notifier_task.cancel()
        try:
            await notifier_task
        except asyncio.CancelledError:
            pass


def run() -> None:
    asyncio.run(main())
