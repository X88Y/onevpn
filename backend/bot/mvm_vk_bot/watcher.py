import hashlib
import logging
import signal
import subprocess
import sys
import time
import uuid

from mvm_bot.constants import BOT_DIR
from mvm_bot.firebase_client import (
    get_vk_tokens_from_db,
    update_vk_token_start_identifier,
)

logger = logging.getLogger(__name__)


def run_watcher() -> None:
    # Sync environment variables to Firestore first
    from mvm_bot.config import vk_bot_tokens
    try:
        logger.info("Syncing environment VK tokens to Firestore...")
        vk_bot_tokens()
    except Exception as e:
        logger.error(f"Failed to sync environment tokens to Firestore: {e}")

    # 1. Generate unique start identifier
    start_id = f"watcher_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    logger.info(f"Starting VK Watcher session with identifier: {start_id}")

    running_processes: dict[str, subprocess.Popen] = {}
    running_tokens: dict[str, str] = {}

    def cleanup_on_exit(signum, frame):
        logger.info("Watcher received termination signal. Cleaning up child processes...")
        # Reset start_identifiers in Firestore
        for token_hash, token in list(running_tokens.items()):
            try:
                logger.info(f"Resetting start_identifier for VK token {token[:8]} in Firestore...")
                update_vk_token_start_identifier(token, None)
            except Exception as e:
                logger.error(f"Failed to reset start_identifier for token {token[:8]}: {e}")

        # Terminate all child processes
        for token_hash, proc in list(running_processes.items()):
            try:
                logger.info(f"Terminating child process PID {proc.pid}...")
                proc.terminate()
            except Exception as e:
                logger.error(f"Failed to terminate child process PID {proc.pid}: {e}")

        # Wait for termination
        for token_hash, proc in list(running_processes.items()):
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
            # Poll all tokens from Firestore
            tokens = get_vk_tokens_from_db()
            active_hashes = set()

            for token in tokens:
                token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
                active_hashes.add(token_hash)

                # Check if process is already running
                if token_hash in running_processes:
                    proc = running_processes[token_hash]
                    # Check if process has died
                    if proc.poll() is not None:
                        logger.warning(
                            f"Child process for token {token[:8]} (PID {proc.pid}) terminated with return code {proc.returncode}."
                        )
                        del running_processes[token_hash]
                        running_tokens.pop(token_hash, None)
                        # Reset identifier in Firebase
                        try:
                            update_vk_token_start_identifier(token, None)
                        except Exception:
                            pass

                # If not running (newly added or crashed), spawn process
                if token_hash not in running_processes:
                    logger.info(f"Spawning individual process for VK token: {token[:8]}...")
                    try:
                        # Spawn vk_bot.py with --token argument and unbuffered output (-u)
                        cmd = [sys.executable, "-u", "vk_bot.py", "--token", token]
                        proc = subprocess.Popen(
                            cmd,
                            cwd=str(BOT_DIR),
                            stdout=None,
                            stderr=None,
                        )
                        running_processes[token_hash] = proc
                        running_tokens[token_hash] = token

                        # Set new start_identifier in Firebase
                        logger.info(f"Updating token {token[:8]} start_identifier to {start_id} in Firestore...")
                        update_vk_token_start_identifier(token, start_id)
                    except Exception as e:
                        logger.error(f"Failed to spawn process or update identifier for token {token[:8]}: {e}")

            # If a running token was removed or set to inactive in DB, stop its process
            for token_hash in list(running_processes.keys()):
                if token_hash not in active_hashes:
                    token = running_tokens.get(token_hash)
                    logger.info(f"Token {token[:8] if token else token_hash[:8]} was removed/disabled from Firestore. Stopping process...")
                    proc = running_processes[token_hash]
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    running_processes.pop(token_hash, None)
                    running_tokens.pop(token_hash, None)
                    if token:
                        try:
                            update_vk_token_start_identifier(token, None)
                        except Exception:
                            pass

        except Exception as e:
            logger.error(f"Error in watcher poll cycle: {e}")

        # Sleep before the next poll cycle
        time.sleep(10)
