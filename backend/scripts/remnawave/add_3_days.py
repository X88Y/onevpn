#!/usr/bin/env python3
"""Add 3 days of subscription time for expired Remnawave users."""

import sys
from pathlib import Path
import os
import argparse
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("add_2_days")

# Discover directories
script_dir = Path(__file__).resolve().parent
# Script is in backend/scripts/remnawave/add_3_days.py
backend_dir = script_dir.parent.parent
bot_dir = backend_dir / "bot"
if not bot_dir.is_dir():
    logger.error(f"Cannot find bot/ directory at {bot_dir}. Ensure you run this script within the backend context.")
    sys.exit(1)

# Add bot directory to python path
sys.path.insert(0, str(bot_dir))

def parse_args():
    parser = argparse.ArgumentParser(
        description="Add 3 days of subscription time for expired Remnawave users."
    )
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="Path to .env file to load (defaults to bot/.env or server_manager/.env)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without modifying Firestore or Remnawave."
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=20,
        help="Number of concurrent update tasks (default: 20)."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose debug logs."
    )
    return parser.parse_args()

async def main():
    args = parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Resolve env path
    env_path = args.env
    if env_path:
        target_env = Path(env_path)
    else:
        if (bot_dir / ".env").exists():
            target_env = bot_dir / ".env"
        elif (backend_dir / "server_manager" / ".env").exists():
            target_env = backend_dir / "server_manager" / ".env"
        else:
            target_env = Path(".env")

    if target_env.exists():
        load_dotenv(target_env)
        logger.info(f"Loaded environment from {target_env}")
    else:
        logger.warning(f"Environment file {target_env} not found, relying on system env.")

    # Import modules now that env vars are loaded
    try:
        from firebase_admin import firestore
        from mvm_bot.firebase_client import init_firebase
        from mvm_bot.datetime_utils import as_utc_datetime
        from mvm_bot.user_service.remnawave import _update_remnawave_subscription
    except ImportError as e:
        logger.error(f"Failed to import dependencies: {e}. Are you inside the correct virtual environment?")
        sys.exit(1)

    base_url = os.getenv("REMNAWAVE_BASE_URL")
    api_token = os.getenv("REMNAWAVE_API_TOKEN")

    if not base_url or not api_token:
        logger.error("REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN must be set in env or .env file.")
        sys.exit(1)

    logger.info("Initializing Firebase...")
    db = init_firebase()

    logger.info("Fetching users with remnawaveUuid from Firestore...")
    users_ref = db.collection("users")
    fb_snaps = await asyncio.to_thread(
        lambda: list(users_ref.where("remnawaveUuid", ">", "").stream())
    )
    logger.info(f"Found {len(fb_snaps)} Remnawave users in Firestore.")

    now = datetime.now(timezone.utc)
    expired_users = []
    for snap in fb_snaps:
        user_uid = snap.id
        user_data = snap.to_dict() or {}
        ends_at = as_utc_datetime(user_data.get("subscriptionEndsAt"))
        if ends_at is None or ends_at <= now:
            expired_users.append((user_uid, user_data, ends_at))

    logger.info(f"Found {len(expired_users)} expired Remnawave users out of {len(fb_snaps)} total users.")

    semaphore = asyncio.Semaphore(args.concurrency)
    updated_count = 0

    async def update_user(user_uid, user_data, ends_at):
        nonlocal updated_count
        new_ends_at = now + timedelta(days=2)
        
        async with semaphore:
            logger.info(
                f"User {user_uid}: current expiry {ends_at} (EXPIRED/NONE) -> new expiry {new_ends_at}"
            )
            if not args.dry_run:
                try:
                    # 1. Update Firestore
                    await asyncio.to_thread(
                        lambda: users_ref.document(user_uid).update({
                            "subscriptionEndsAt": new_ends_at,
                            "updatedAt": firestore.SERVER_TIMESTAMP
                        })
                    )
                    
                    # 2. Push update to Remnawave panel
                    await _update_remnawave_subscription(
                        user_uid=user_uid,
                        subscription_ends_at=new_ends_at,
                        tier=user_data.get("subscriptionTier")
                    )
                    logger.info(f"Successfully updated user {user_uid}")
                    updated_count += 1
                except Exception as e:
                    logger.error(f"Failed to update user {user_uid}: {e}")
            else:
                logger.info(f"[Dry Run] Would update user {user_uid} to expire at {new_ends_at}")
                updated_count += 1

    tasks = [update_user(uid, data, exp) for uid, data, exp in expired_users]
    if tasks:
        await asyncio.gather(*tasks)

    logger.info(f"Process complete. Updated {updated_count}/{len(expired_users)} users.")

if __name__ == "__main__":
    asyncio.run(main())
