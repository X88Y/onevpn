import asyncio
import logging

from aiogram import Bot, Dispatcher  # type: ignore[import-not-found]
from aiogram.fsm.storage.memory import MemoryStorage  # type: ignore[import-not-found]
from aiogram.types import BotCommand  # type: ignore[import-not-found]
from dotenv import load_dotenv  # type: ignore[import-not-found]

from mvm_bot.config import bot_token
from mvm_bot.constants import BOT_DIR
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

    await dispatcher.start_polling(bot)


def run() -> None:
    asyncio.run(main())
