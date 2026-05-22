import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

# Load .env BEFORE any project imports that read os.environ at import time
_BOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BOT_DIR / ".env")

from vkbottle import API, Bot, run_multibot

from mvm_bot.config import vk_bot_token, vk_bot_tokens
from mvm_bot.constants import BOT_DIR
from mvm_vk_bot.handlers import register_handlers
from mvm_vk_bot.menu import preupload_menu_banner


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    tokens = vk_bot_tokens()

    if tokens:
        loop = asyncio.get_event_loop()
        try:
            logging.info("Starting VK menu banner pre-upload...")
            loop.run_until_complete(preupload_menu_banner(tokens))
        except Exception as e:
            logging.error(f"Error during VK menu banner pre-upload: {e}")

    bot = Bot()
    register_handlers(bot)
    # bot.run_forever()
    run_multibot(bot, apis=(API(token) for token in tokens))
