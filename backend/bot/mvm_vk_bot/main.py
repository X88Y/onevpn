import argparse
import asyncio
import hashlib
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from vkbottle import API, Bot, run_multibot
from aiohttp import web

# Load .env BEFORE any project imports that read os.environ at import time
_BOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BOT_DIR / ".env")

from mvm_bot.config import vk_bot_token, vk_bot_tokens
from mvm_bot.constants import BOT_DIR
from mvm_bot.firebase_client import (
    get_vk_token_config,
    get_vk_token_configs_from_db,
    update_vk_token_group_id,
    update_vk_token_webhook_setuped,
)
from mvm_vk_bot.handlers import register_handlers
from mvm_vk_bot.menu import preupload_menu_banner
from mvm_vk_bot.watcher import run_watcher


async def setup_vk_callbacks(bots: dict[str, Bot], bot_configs: dict[str, dict]) -> None:
    async def task():
        await asyncio.sleep(1)  # Wait for the web server to start listening
        for token_hash, bot in bots.items():
            cfg = bot_configs[token_hash]
            if cfg.get("webhook_setuped"):
                logging.info(f"VK bot {token_hash[:8]} is already setuped in Firestore. Skipping Callback API setup.")
                continue

            logging.info(f"Setting up VK Callback API for bot {token_hash[:8]}...")
            try:
                # Resolve group_id if not present
                group_id = cfg.get("group_id")
                if not group_id:
                    res = await bot.api.request("groups.getById", {})
                    groups_info = res.get("response", {}).get("groups", [])
                    if groups_info:
                        group_id = groups_info[0].get("id")
                        if group_id:
                            await asyncio.to_thread(update_vk_token_group_id, cfg["token"], group_id)
                            cfg["group_id"] = group_id
                if not group_id:
                    raise ValueError("Failed to resolve group_id for bot")

                # 1. Fetch confirmation code from VK
                res = await bot.api.request("groups.getCallbackConfirmationCode", {"group_id": group_id})
                confirmation_code = res["response"]["code"]
                cfg["webhook_confirmation_code"] = confirmation_code
                logging.info(f"Fetched VK confirmation code for bot {token_hash[:8]}: {confirmation_code[:4]}...")

                # 2. Get webhook URL
                webhook_url = cfg.get("webhook_url")
                if not webhook_url:
                    base_url = os.getenv("VK_WEBHOOK_BASE_URL")
                    if base_url:
                        webhook_url = f"{base_url.rstrip('/')}/{token_hash}"
                    else:
                        raise ValueError(f"webhook_url must be configured in Firestore or VK_WEBHOOK_BASE_URL in .env for bot {token_hash[:8]}")

                # 3. Check existing Callback servers in VK settings
                res = await bot.api.request("groups.getCallbackServers", {"group_id": group_id})
                servers = res.get("response", {}).get("items", [])
                server_id = None
                for s in servers:
                    if s.get("url") == webhook_url:
                        server_id = s.get("id")
                        logging.info(f"Found existing Callback server ID {server_id} for bot {token_hash[:8]}")
                        break

                # 4. Add or edit Callback server (triggers immediate confirmation ping from VK)
                webhook_secret_key = cfg.get("webhook_secret_key") or ""
                if server_id is None:
                    logging.info(f"Adding Callback server for bot {token_hash[:8]} at {webhook_url}...")
                    res = await bot.api.request("groups.addCallbackServer", {
                        "group_id": group_id,
                        "url": webhook_url,
                        "title": "MVM Webhook",
                        "secret_key": webhook_secret_key
                    })
                    server_id = res["response"]["server_id"]
                    logging.info(f"Successfully added Callback server ID {server_id} for bot {token_hash[:8]}")
                else:
                    logging.info(f"Editing Callback server ID {server_id} for bot {token_hash[:8]}...")
                    await bot.api.request("groups.editCallbackServer", {
                        "group_id": group_id,
                        "server_id": server_id,
                        "url": webhook_url,
                        "title": "MVM Webhook",
                        "secret_key": webhook_secret_key
                    })

                # 5. Enable event settings (enable message_new event)
                logging.info(f"Enabling message_new Callback event for bot {token_hash[:8]} server ID {server_id}...")
                await bot.api.request("groups.setCallbackSettings", {
                    "group_id": group_id,
                    "server_id": server_id,
                    "message_new": 1
                })

                # 6. Update Firestore
                await asyncio.to_thread(update_vk_token_webhook_setuped, cfg["token"], True, server_id)
                cfg["webhook_setuped"] = True
                cfg["webhook_server_id"] = server_id
                logging.info(f"VK bot {token_hash[:8]} Callback API successfully configured and marked as setuped!")

            except Exception as e:
                logging.error(f"Failed to setup Callback API for bot {token_hash[:8]}: {e}")

    asyncio.create_task(task())


async def start_web_app(app: web.Application, host: str, port: int) -> None:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logging.info(f"Unified web server successfully bound to http://{host}:{port}")
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()


def run() -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="MVM VK Bot / Watcher")
    parser.add_argument("--token", type=str, help="Specific VK bot token to run")
    parser.add_argument("--webhooks", action="store_true", help="Run all webhook bots in this single process")
    args, unknown = parser.parse_known_args()

    if args.token:
        token = args.token
        logging.info(f"Starting VK bot instance for token {token[:8]}...")

        loop = asyncio.get_event_loop()
        try:
            logging.info("Starting VK menu banner pre-upload...")
            loop.run_in_executor(preupload_menu_banner([token]))
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
                        await asyncio.to_thread(update_vk_token_group_id, token, g_id)
            logging.info("Resolving VK group ID...")
            loop.run_until_complete(resolve_and_save_group_id())
        except Exception as e:
            logging.error(f"Error resolving or saving VK group ID: {e}")

        # Fetch configuration from Firestore
        config = get_vk_token_config(token) or {}
        working_mode = config.get("working_mode", "long_poll")

        # Explicit validation and fail fast
        if working_mode == "webhook":
            webhook_port_val = config.get("webhook_port")
            if webhook_port_val is None:
                raise ValueError(f"webhook_port must be configured in Firestore for token {token[:8]} in webhook mode")
            try:
                webhook_port = int(webhook_port_val)
            except ValueError:
                raise ValueError(f"webhook_port must be a valid integer, got {webhook_port_val}")

            webhook_url = config.get("webhook_url")
            if not webhook_url and not os.getenv("VK_WEBHOOK_BASE_URL"):
                raise ValueError(f"webhook_url must be configured in Firestore or VK_WEBHOOK_BASE_URL in .env for token {token[:8]} in webhook mode")

            webhook_host = config.get("webhook_host") or "0.0.0.0"
            webhook_secret_key = config.get("webhook_secret_key")

            # Initialize bot with token
            bot = Bot(token=token)
            register_handlers(bot)

            # Define Webhook App
            app = web.Application()

            async def vk_handler(request: web.Request) -> web.StreamResponse:
                try:
                    data = await request.json()
                except Exception:
                    return web.Response(text="invalid json", status=400)
                logging.info(f"Received VK webhook request: {data}")
                webhook_confirmation_code = config.get("webhook_confirmation_code")

                if data.get("type") == "confirmation":
                    if not webhook_confirmation_code:
                        logging.warning(f"Confirmation code not yet available in memory for token {token[:8]}. Waiting...")
                        for _ in range(50):
                            await asyncio.sleep(0.1)
                            webhook_confirmation_code = config.get("webhook_confirmation_code")
                            if webhook_confirmation_code:
                                break
                    if not webhook_confirmation_code:
                        logging.error(f"Confirmation code still missing for token {token[:8]}")
                        return web.Response(text="missing confirmation code", status=500)
                    logging.info(f"Sending VK confirmation code for token {token[:8]}...")
                    return web.Response(text=webhook_confirmation_code)

                if webhook_secret_key and data.get("secret") != webhook_secret_key:
                    logging.warning(f"Forbidden: invalid secret key for token {token[:8]}")
                    return web.Response(text="forbidden", status=403)

                # Process event in background to avoid timeouts
                asyncio.create_task(bot.process_event(data))
                return web.Response(text="ok")

            app.router.add_post("/{tail:.*}", vk_handler)

            token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
            bots = {token_hash: bot}
            bot_configs = {token_hash: config}

            async def on_startup(a):
                await setup_vk_callbacks(bots, bot_configs)

            app.on_startup.append(on_startup)

            logging.info(f"Starting VK bot in Webhook mode on {webhook_host}:{webhook_port}...")
            loop.run_until_complete(start_web_app(app, webhook_host, webhook_port))

        else:
            logging.info(f"Starting VK bot in Long Poll mode for token {token[:8]}...")
            bot = Bot()
            register_handlers(bot)
            run_multibot(bot, apis=[API(token)])

    elif args.webhooks:
        logging.info("Starting VK bots in multi-webhook mode...")

        # 1. Fetch all configurations from Firestore
        configs = get_vk_token_configs_from_db()
        webhook_configs = [c for c in configs if c.get("working_mode") == "webhook" and c.get("token")]
        logging.info("fetched tokens")
        if not webhook_configs:
            logging.warning("No webhook bots configured in Firestore. Exiting...")
            return

        # 2. Pre-upload banners for all webhook bot tokens
        loop = asyncio.get_event_loop()
        webhook_tokens = [c["token"] for c in webhook_configs]
        try:
            logging.info("Starting VK menu banner pre-upload for all webhook bots...")
            loop.run_in_executor(preupload_menu_banner(webhook_tokens))
        except Exception as e:
            logging.error(f"Error during VK menu banner pre-upload: {e}")

        # 3. Resolve group_ids and save to Firestore
        try:
            async def resolve_all_group_ids():
                for cfg in webhook_configs:
                    token = cfg["token"]
                    try:
                        api = API(token)
                        res = await api.request("groups.getById", {})
                        groups_info = res.get("response", {}).get("groups", [])
                        if groups_info:
                            g_id = groups_info[0].get("id")
                            if g_id:
                                await asyncio.to_thread(update_vk_token_group_id, token, g_id)
                    except Exception as ex:
                        logging.error(f"Error resolving group ID for token {token[:8]}: {ex}")

            logging.info("Resolving VK group IDs for all webhook bots...")
            loop.run_until_complete(resolve_all_group_ids())
        except Exception as e:
            logging.error(f"Error resolving VK group IDs: {e}")

        # 4. Resolve the webhook port (fail fast if invalid/conflicting)
        webhook_port_env = os.getenv("VK_WEBHOOK_PORT")
        if webhook_port_env:
            try:
                webhook_port = int(webhook_port_env)
            except ValueError:
                raise ValueError(f"VK_WEBHOOK_PORT env var must be an integer, got {webhook_port_env}")
        else:
            ports = {cfg.get("webhook_port") for cfg in webhook_configs if cfg.get("webhook_port") is not None}
            if not ports:
                raise ValueError("No webhook port configured. Please set VK_WEBHOOK_PORT in bot/.env or configure webhook_port in Firestore.")
            if len(ports) > 1:
                raise ValueError(
                    f"Multiple conflicting webhook ports configured in Firestore: {ports}. "
                    "Since all webhook bots run in one process, please specify a single port using VK_WEBHOOK_PORT in bot/.env."
                )
            webhook_port = int(list(ports)[0])

        # 5. Initialize Bots and store by token_hash
        bots: dict[str, Bot] = {}
        bot_configs: dict[str, dict] = {}

        for cfg in webhook_configs:
            token = cfg["token"]
            token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()

            webhook_url = cfg.get("webhook_url")
            if not webhook_url and not os.getenv("VK_WEBHOOK_BASE_URL"):
                raise ValueError(f"webhook_url must be configured in Firestore or VK_WEBHOOK_BASE_URL in .env for token {token[:8]} in webhook mode")

            bot = Bot(token=token)
            register_handlers(bot)
            bots[token_hash] = bot
            bot_configs[token_hash] = cfg

        # 6. Default host and create web server
        webhook_host = os.getenv("VK_WEBHOOK_HOST") or "0.0.0.0"
        app = web.Application()

        async def vk_multihandler(request: web.Request) -> web.StreamResponse:
            # Extract last segment of the path as the token hash
            path_parts = [p for p in request.path.split('/') if p]
            if not path_parts:
                return web.Response(text="not found", status=404)
            token_hash = path_parts[-1]

            bot = bots.get(token_hash)
            cfg = bot_configs.get(token_hash)
            if not bot or not cfg:
                return web.Response(text="bot not found", status=404)

            try:
                data = await request.json()
            except Exception:
                return web.Response(text="invalid json", status=400)

            webhook_confirmation_code = cfg.get("webhook_confirmation_code")
            webhook_secret_key = cfg.get("webhook_secret_key")

            if data.get("type") == "confirmation":
                if not webhook_confirmation_code:
                    logging.warning(f"Confirmation code not yet available in memory for token {token_hash[:8]}. Waiting...")
                    for _ in range(50):
                        await asyncio.sleep(0.1)
                        webhook_confirmation_code = cfg.get("webhook_confirmation_code")
                        if webhook_confirmation_code:
                            break
                if not webhook_confirmation_code:
                    logging.error(f"Confirmation code still missing for token {token_hash[:8]}")
                    return web.Response(text="missing confirmation code", status=500)
                logging.info(f"Sending VK confirmation code for token {token_hash[:8]}...")
                return web.Response(text=webhook_confirmation_code)

            if webhook_secret_key and data.get("secret") != webhook_secret_key:
                logging.warning(f"Forbidden: invalid secret key for token {token_hash[:8]}")
                return web.Response(text="forbidden", status=403)

            # Process event in background to avoid timeouts
            asyncio.create_task(bot.process_event(data))
            return web.Response(text="ok")

        app.router.add_post("/{tail:.*}", vk_multihandler)

        async def on_startup(a):
            await setup_vk_callbacks(bots, bot_configs)

        app.on_startup.append(on_startup)

        logging.info(f"Starting unified VK webhook server on {webhook_host}:{webhook_port} for {len(bots)} bots...")
        loop.run_until_complete(start_web_app(app, webhook_host, webhook_port))

    else:
        logging.info("Starting VK Bot Watcher...")
        run_watcher()

