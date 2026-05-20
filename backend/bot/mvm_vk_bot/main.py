import logging
from pathlib import Path

from dotenv import load_dotenv

# Load .env BEFORE any project imports that read os.environ at import time
_BOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BOT_DIR / ".env")

from vkbottle import API, Bot, run_multibot

from mvm_bot.config import vk_bot_tokens
from mvm_vk_bot.handlers import register_handlers


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    tokens = vk_bot_tokens()
    if not tokens:
        raise RuntimeError(
            "No VK bot tokens configured. Set VK_BOT_TOKENS or VK_BOT_TOKEN in bot/.env"
        )

    bot = Bot()
    register_handlers(bot)

    apis = tuple(API(token) for token in tokens)
    run_multibot(bot, apis=apis)
