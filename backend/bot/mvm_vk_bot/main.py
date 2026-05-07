import logging

from dotenv import load_dotenv
from vkbottle import Bot

from mvm_bot.config import vk_bot_token
from mvm_bot.constants import BOT_DIR
from mvm_vk_bot.handlers import register_handlers


def run() -> None:
    load_dotenv(BOT_DIR / ".env")
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=vk_bot_token())
    register_handlers(bot)
    bot.run_forever()
