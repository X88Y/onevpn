import logging
from pathlib import Path

from dotenv import load_dotenv

# Load .env BEFORE any project imports that read os.environ at import time
_BOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BOT_DIR / ".env")

from vkbottle import Bot

from mvm_bot.config import vk_bot_token
from mvm_bot.constants import BOT_DIR
from mvm_vk_bot.handlers import register_handlers


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=vk_bot_token())
    register_handlers(bot)
    bot.run_forever()
