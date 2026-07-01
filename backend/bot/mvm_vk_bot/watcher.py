import hashlib
import logging
import signal
import subprocess
import sys
import time
import uuid

from mvm_bot.config import vk_bot_tokens
from mvm_bot.constants import BOT_DIR
from mvm_bot.firebase_client import (
    get_vk_token_configs_from_db,
    update_vk_token_start_identifier,
)

logger = logging.getLogger(__name__)


def run_watcher() -> None:
    # Sync environment variables to Firestore first
    try:
        logger.info("Syncing environment VK tokens to Firestore...")
        vk_bot_tokens()
    except Exception as e:
        logger.error(f"Failed to sync environment tokens to Firestore: {e}")

    # 1. Generate unique start identifier
    start_id = f"watcher_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    logger.info(f"Starting VK Watcher session with identifier: {start_id}")

    running_processes: dict[str, subprocess.Popen] = {}
    running_tokens: dict[str, str | list[str]] = {}

    def cleanup_on_exit(signum, frame):
        logger.info("Watcher received termination signal. Cleaning up child processes...")
        # Reset start_identifiers in Firestore
        for config_hash, token_val in list(running_tokens.items()):
            tokens_to_reset = token_val if isinstance(token_val, list) else [token_val]
            for token in tokens_to_reset:
                try:
                    logger.info(f"Resetting start_identifier for VK token {token[:8]} in Firestore...")
                    update_vk_token_start_identifier(token, None)
                except Exception as e:
                    logger.error(f"Failed to reset start_identifier for token {token[:8]}: {e}")

        # Terminate all child processes
        for config_hash, proc in list(running_processes.items()):
            try:
                logger.info(f"Terminating child process PID {proc.pid}...")
                proc.terminate()
            except Exception as e:
                logger.error(f"Failed to terminate child process PID {proc.pid}: {e}")

        # Wait for termination
        for config_hash, proc in list(running_processes.items()):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f"Process PID {proc.pid} did not exit in time. Killing it...")
                proc.kill()
            except Exception:
                pass

        logger.info("Watcher exit cleanup complete.")
        sys.exit(0)

    # Register signals for graceful shutdown
    signal.signal(signal.SIGINT, cleanup_on_exit)
    signal.signal(signal.SIGTERM, cleanup_on_exit)

    # Watcher poll loop
    while True:
        try:
            # Poll all active token configs from Firestore
            configs = get_vk_token_configs_from_db()
            active_hashes = set()

            # Separate long poll and webhook configs
            long_poll_configs = []
            webhook_configs = []

            for config_data in configs:
                token = config_data.get("token")
                if not token:
                    continue
                working_mode = config_data.get("working_mode", "long_poll")
                if working_mode == "webhook":
                    webhook_configs.append(config_data)
                else:
                    long_poll_configs.append(config_data)

            # Process individual long poll bots
            for config_data in long_poll_configs:
                token = config_data["token"]
                config_hash = hashlib.sha256(f"{token}:long_poll".encode('utf-8')).hexdigest()
                active_hashes.add(config_hash)

                # Check if process is already running
                if config_hash in running_processes:
                    proc = running_processes[config_hash]
                    # Check if process has died
                    if proc.poll() is not None:
                        logger.warning(
                            f"Child process for long_poll token {token[:8]} (PID {proc.pid}) terminated with return code {proc.returncode}."
                        )
                        del running_processes[config_hash]
                        running_tokens.pop(config_hash, None)
                        try:
                            update_vk_token_start_identifier(token, None)
                        except Exception:
                            pass

                # If not running, spawn process
                if config_hash not in running_processes:
                    logger.info(f"Spawning individual long_poll process for VK token: {token[:8]}...")
                    try:
                        cmd = [sys.executable, "-u", "vk_bot.py", "--token", token]
                        proc = subprocess.Popen(
                            cmd,
                            cwd=str(BOT_DIR),
                            stdout=None,
                            stderr=None,
                            close_fds=True,
                        )
                        running_processes[config_hash] = proc
                        running_tokens[config_hash] = token

                        logger.info(f"Updating token {token[:8]} start_identifier to {start_id} in Firestore...")
                        update_vk_token_start_identifier(token, start_id)
                    except Exception as e:
                        logger.error(f"Failed to spawn process or update identifier for token {token[:8]}: {e}")

            # Process all webhook bots in a single process
            if webhook_configs:
                # Deterministic sorting to ensure stable combined hash
                webhook_configs.sort(key=lambda c: c["token"])

                webhook_token_config_strs = []
                webhook_tokens_list = []
                for config_data in webhook_configs:
                    token = config_data["token"]
                    webhook_tokens_list.append(token)
                    working_mode = config_data.get("working_mode", "long_poll")
                    webhook_url = config_data.get("webhook_url", "")
                    webhook_port = config_data.get("webhook_port", "")
                    webhook_confirmation_code = config_data.get("webhook_confirmation_code", "")
                    webhook_secret_key = config_data.get("webhook_secret_key", "")
                    webhook_host = config_data.get("webhook_host", "")
                    webhook_token_config_strs.append(
                        f"{token}:{working_mode}:{webhook_url}:{webhook_port}:{webhook_confirmation_code}:{webhook_secret_key}:{webhook_host}"
                    )
                combined_str = "|".join(webhook_token_config_strs)
                combined_webhook_hash = hashlib.sha256(combined_str.encode('utf-8')).hexdigest()
                active_hashes.add(combined_webhook_hash)

                # Check if process is already running
                if combined_webhook_hash in running_processes:
                    proc = running_processes[combined_webhook_hash]
                    # Check if process has died
                    if proc.poll() is not None:
                        logger.warning(
                            f"Child process for all webhook bots (PID {proc.pid}) terminated with return code {proc.returncode}."
                        )
                        del running_processes[combined_webhook_hash]
                        running_tokens.pop(combined_webhook_hash, None)
                        for token in webhook_tokens_list:
                            try:
                                update_vk_token_start_identifier(token, None)
                            except Exception:
                                pass

                # If not running (newly added, config changed, or crashed), spawn process
                if combined_webhook_hash not in running_processes:
                    logger.info(f"Spawning single process for all webhook bots (hash: {combined_webhook_hash[:8]})...")
                    try:
                        cmd = [sys.executable, "-u", "vk_bot.py", "--webhooks"]
                        proc = subprocess.Popen(
                            cmd,
                            cwd=str(BOT_DIR),
                            stdout=None,
                            stderr=None,
                            close_fds=True,
                        )
                        running_processes[combined_webhook_hash] = proc
                        running_tokens[combined_webhook_hash] = webhook_tokens_list

                        for token in webhook_tokens_list:
                            logger.info(f"Updating token {token[:8]} start_identifier to {start_id} in Firestore...")
                            update_vk_token_start_identifier(token, start_id)
                    except Exception as e:
                        logger.error(f"Failed to spawn process or update identifier for webhook bots: {e}")

            # Clean up processes that are no longer active (disabled, removed, or configuration updated)
            for config_hash in list(running_processes.keys()):
                if config_hash not in active_hashes:
                    token_val = running_tokens.get(config_hash)
                    tokens_to_reset = token_val if isinstance(token_val, list) else [token_val]
                    logger.info(f"Process with hash {config_hash[:8]} was removed or configuration updated. Stopping process...")
                    proc = running_processes[config_hash]
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    running_processes.pop(config_hash, None)
                    running_tokens.pop(config_hash, None)
                    for token in tokens_to_reset:
                        if token:
                            try:
                                update_vk_token_start_identifier(token, None)
                            except Exception:
                                pass

        except Exception as e:
            logger.error(f"Error in watcher poll cycle: {e}")

        # Sleep before the next poll cycle
        time.sleep(10)
