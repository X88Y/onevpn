import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

# Load .env BEFORE any project imports that read os.environ at import time
_BOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BOT_DIR / ".env")

from vkbottle import Bot

from mvm_bot.config import vk_bot_tokens
from mvm_vk_bot.handlers import register_handlers


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    tokens = vk_bot_tokens()
    if not tokens:
        raise RuntimeError(
            "No VK bot tokens configured. Set VK_BOT_TOKENS or VK_BOT_TOKEN in bot/.env"
        )

    bots: list[Bot] = []
    for token in tokens:
        bot = Bot(token=token)
        register_handlers(bot)
        bots.append(bot)

    logger = logging.getLogger(__name__)
    logger.info("Starting %s VK bot instance(s)", len(bots))

    async def _run_all() -> None:
        await asyncio.gather(*(bot.run_polling() for bot in bots))

    asyncio.run(_run_all())
