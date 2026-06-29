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


import argparse


def run() -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="MVM VK Bot / Watcher")
    parser.add_argument("--token", type=str, help="Specific VK bot token to run")
    args, unknown = parser.parse_known_args()

    if args.token:
        token = args.token
        logging.info(f"Starting VK bot instance for token {token[:8]}...")

        loop = asyncio.get_event_loop()
        try:
            logging.info("Starting VK menu banner pre-upload...")
            loop.run_until_complete(preupload_menu_banner([token]))
        except Exception as e:
            logging.error(f"Error during VK menu banner pre-upload: {e}")

        # Resolve group_id and update in Firestore if not exists
        try:
            async def resolve_and_save_group_id():
                api = API(token)
                res = await api.request("groups.getById", {})
                groups_info = res.get("response", {}).get("groups", [])
                if groups_info:
                    g_id = groups_info[0].get("id")
                    if g_id:
                        from mvm_bot.firebase_client import update_vk_token_group_id
                        await asyncio.to_thread(update_vk_token_group_id, token, g_id)
            logging.info("Resolving VK group ID...")
            loop.run_until_complete(resolve_and_save_group_id())
        except Exception as e:
            logging.error(f"Error resolving or saving VK group ID: {e}")

        bot = Bot()
        register_handlers(bot)
        run_multibot(bot, apis=[API(token)])
    else:
        logging.info("Starting VK Bot Watcher...")
        from mvm_vk_bot.watcher import run_watcher
        run_watcher()

