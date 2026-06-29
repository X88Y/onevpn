import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from dotenv import load_dotenv

from bot_admin.config import bot_token
from bot_admin.constants import BOT_ADMIN_DIR
from bot_admin.handlers import router


async def _main() -> None:
    load_dotenv(BOT_ADMIN_DIR / ".env")
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=bot_token())
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Help"),
            BotCommand(command="stats", description="Get purchase & conversion statistics"),
            BotCommand(command="group_stats", description="VK group payment & conversion stats"),
            BotCommand(command="add_server", description="Add a VPN server"),
            BotCommand(command="list_servers", description="List VPN servers (paginated)"),
            BotCommand(command="list_server", description="List VPN servers (paginated)"),
            BotCommand(command="disable_server", description="Disable server <id>"),
            BotCommand(command="enable_server", description="Enable server <id>"),
            BotCommand(command="create_promocode", description="Create or update promo code"),
            BotCommand(command="delete_promocode", description="Delete promo code by value"),
            BotCommand(command="promo_stats", description="Show promo usage statistics"),
            BotCommand(command="create_tw_cdn", description="Create TimeWeb CDNs with token"),
            BotCommand(command="cancel", description="Cancel current flow"),
        ]
    )

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot)


def run() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    run()
