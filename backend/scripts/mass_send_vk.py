#!/usr/bin/env python3
"""Mass send message to VK users and extend their subscription by +2 days."""

import sys
from pathlib import Path
import os
import argparse
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional
import aiohttp
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("mass_send_vk")

# Discover directories
script_dir = Path(__file__).resolve().parent
bot_dir = script_dir / "bot"
if not bot_dir.is_dir():
    if (script_dir / "mvm_bot").is_dir():
        bot_dir = script_dir
    else:
        logger.error("Cannot find bot/ directory. Ensure you run this from backend/")
        sys.exit(1)

# Add bot directory to python path
sys.path.insert(0, str(bot_dir))

def parse_args():
    parser = argparse.ArgumentParser(
        description="Mass send a VK message to VK users and extend subscription by N days."
    )
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="Path to .env file to load (defaults to bot/.env)."
    )
    parser.add_argument(
        "--message",
        type=str,
        default=(
            "Если ВПН перестал работать, не пугайтесь❗️\n\n"
            "Мы обновили сервера и исправили мелкие ошибки. \n\n"
            "Что бы возобновить работу ВПН: \n"
            "— Удалите старое подключение.\n"
            "— Нажмите в этом сообщение на кнопку «Подключить» и добавьте подписку еще раз👇👇\n\n"
            "В качестве извинений за предоставленные неудобства дарим вам +2 дня бесплатного пользования🫶"
        ),
        help="Message to send to VK users."
    )
    parser.add_argument(
        "--images",
        type=str,
        nargs="*",
        default=None,
        help="List of image paths to attach (defaults to 1.jpg and 2.jpg in backend/assets)."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=2,
        help="Number of days to add to subscription (default: 2)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of users to process."
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default=None,
        help="Process only a single user with this document ID or VK ID."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run (no actual VK messages sent, no DB updates)."
    )
    parser.add_argument(
        "--skip-msg-failures",
        action="store_true",
        help="If set, do not update Firestore/Remnawave for users where message failed on all tokens."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose debug logs."
    )
    return parser.parse_args()

def _extract_provider_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value)
    if s.startswith("tg:"):
        return s[3:]
    if s.startswith("vk:"):
        return s[3:]
    return s

# Cache to avoid uploading the same images multiple times per token
_uploaded_attachments_cache = {}

async def _get_or_upload_attachments(token: str, image_paths: List[Path]) -> Optional[str]:
    if token in _uploaded_attachments_cache:
        return _uploaded_attachments_cache[token]

    # Check Firestore cache first
    keys = [path.name for path in image_paths if path.exists()]
    if keys:
        try:
            from mvm_bot.firebase_client import get_vk_cached_attachment
            cached = await get_vk_cached_attachment(token, keys)
            if cached:
                _uploaded_attachments_cache[token] = cached
                logger.info(f"Loaded attachments from Firestore cache for token {token[:8]}: {cached}")
                return cached
        except Exception as e:
            logger.error(f"Failed to check Firestore cache: {e}")

    from vkbottle import API
    from vkbottle.tools import PhotoMessageUploader

    api = API(token)
    uploader = PhotoMessageUploader(api)
    uploaded_ids = []

    for path in image_paths:
        if not path.exists():
            logger.warning(f"Image path does not exist: {path}")
            continue
        
        attempts = 5
        success = False
        for attempt in range(1, attempts + 1):
            try:
                logger.info(f"Uploading photo {path.name} for token {token[:8]} (attempt {attempt}/{attempts})...")
                attachment_str = await uploader.upload(file_source=str(path))
                uploaded_ids.append(attachment_str)
                success = True
                break
            except Exception as e:
                logger.error(f"Failed to upload photo {path.name} for token {token[:8]} (attempt {attempt}/{attempts}): {e}")
                if attempt < attempts:
                    await asyncio.sleep(3)
        if not success:
            logger.error(f"Failed to upload photo {path.name} for token {token[:8]} after all attempts.")

    if uploaded_ids:
        attachment_str = ",".join(uploaded_ids)
        _uploaded_attachments_cache[token] = attachment_str
        if keys:
            try:
                from mvm_bot.firebase_client import set_vk_cached_attachment
                await set_vk_cached_attachment(token, keys, attachment_str)
                logger.info(f"Saved attachments to Firestore cache for token {token[:8]}: {attachment_str}")
            except Exception as e:
                logger.error(f"Failed to save to Firestore cache: {e}")
        return attachment_str
    return None

async def _notify_vk_with_token(
    user_id: str,
    text: str,
    token: str,
    keyboard: Optional[str] = None,
    attachment: Optional[str] = None
) -> bool:
    params = {
        "user_id": user_id,
        "message": text,
        "random_id": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
        "access_token": token,
        "v": "5.231",
    }
    if keyboard:
        params["keyboard"] = keyboard
    if attachment:
        params["attachment"] = attachment
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.vk.com/method/messages.send", params=params
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(
                        "VK send failed for user %s (token=%s...): HTTP %s %s",
                        user_id,
                        token[:8],
                        resp.status,
                        body,
                    )
                    return False
                data = await resp.json()
                if data.get("error"):
                    logger.warning(
                        "VK API error for user %s (token=%s...): %s",
                        user_id,
                        token[:8],
                        data["error"],
                    )
                    return False
                return True
    except Exception:
        logger.exception("VK send error for user %s (token=%s...)", user_id, token[:8])
        return False

async def send_vk_message(
    vk_id: str,
    text: str,
    tokens: List[str],
    image_paths: List[Path],
    keyboard: Optional[str] = None,
    dry_run: bool = False
) -> bool:
    if dry_run:
        img_names = [p.name for p in image_paths]
        logger.info(f"[Dry Run] Would send to VK user {vk_id}: '{text}' with images {img_names} (keyboard={keyboard})")
        return True

    if not tokens:
        logger.error("No VK bot tokens available.")
        return False

    for token in tokens:
        attachment = await _get_or_upload_attachments(token, image_paths)
        success = await _notify_vk_with_token(vk_id, text, token, keyboard=keyboard, attachment=attachment)
        if success:
            logger.info(f"Successfully sent message to VK user {vk_id} using token {token[:8]}...")
            return True
        else:
            logger.warning(f"Token {token[:8]}... failed for user {vk_id}. Trying next token...")

    logger.error(f"Failed to send message to VK user {vk_id} using all available tokens.")
    return False

async def main():
    args = parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Resolve image paths
    if args.images is not None:
        image_paths = [Path(p) for p in args.images]
    else:
        # Default to 1.jpg and 2.jpg in assets/
        assets_dir = script_dir / "assets"
        image_paths = [assets_dir / "1.jpg", assets_dir / "2.jpg"]

    # Resolve env path
    env_path = args.env
    if env_path:
        target_env = Path(env_path)
    else:
        # Try bot/.env first, then server_manager/.env
        if (bot_dir / ".env").exists():
            target_env = bot_dir / ".env"
        elif (script_dir / "server_manager" / ".env").exists():
            target_env = script_dir / "server_manager" / ".env"
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
        from mvm_bot.config import vk_bot_tokens
        from mvm_bot.user_service import _update_remnawave_subscription
    except ImportError as e:
        logger.error(f"Failed to import dependencies: {e}. Are you inside the correct virtual environment?")
        sys.exit(1)

    tokens = vk_bot_tokens()
    if not tokens:
        logger.error("No VK_BOT_TOKENS or VK_BOT_TOKEN found in environment/env file.")
        sys.exit(1)
    logger.info(f"Loaded {len(tokens)} VK bot token(s).")

    # Pre-upload images/attachments at startup (with retries inside _get_or_upload_attachments)
    if not args.dry_run and image_paths:
        logger.info("Pre-uploading VK images/attachments for all tokens...")
        for token in tokens:
            await _get_or_upload_attachments(token, image_paths)

    db = init_firebase()
    users_ref = db.collection("users")

    logger.info("Fetching users with VK integration from Firestore...")
    
    # Query only users where externalVk is present
    if args.user_id:
        # Try finding by document ID first, then fallback to querying by externalVk
        doc = await asyncio.to_thread(users_ref.document(args.user_id).get)
        if doc.exists:
            fb_snaps = [doc]
        else:
            # Query by externalVk matching exact ID or with "vk:" prefix
            candidates = [args.user_id, f"vk:{args.user_id}"]
            fb_snaps = await asyncio.to_thread(
                lambda: list(users_ref.where("externalVk", "in", candidates).stream())
            )
    else:
        fb_snaps = await asyncio.to_thread(
            lambda: list(users_ref.where("externalVk", "!=", None).stream())
        )

    logger.info(f"Found {len(fb_snaps)} candidate user(s) with VK integration.")

    processed_count = 0
    success_msg_count = 0
    fail_msg_count = 0
    updated_db_count = 0
    skipped_db_count = 0

    for snap in fb_snaps:
        if args.limit and processed_count >= args.limit:
            logger.info(f"Reached limit of {args.limit} users. Stopping.")
            break

        user_uid = snap.id
        user_data = snap.to_dict() or {}
        external_vk = user_data.get("externalVk")
        vk_id = _extract_provider_id(external_vk)

        if not vk_id:
            logger.warning(f"Skipping user {user_uid}: externalVk is invalid ({external_vk})")
            continue

        processed_count += 1
        logger.info(f"[{processed_count}/{len(fb_snaps)}] Processing user {user_uid} (VK ID: {vk_id})...")

        # Check if subscription has ended
        ends_at = as_utc_datetime(user_data.get("subscriptionEndsAt"))
        now = datetime.now(timezone.utc)
        if not ends_at or ends_at <= now:
            logger.info(f"Skipping user {user_uid}: subscription has ended or is inactive.")
            skipped_db_count += 1
            continue

        # Build keyboard with connection button if subscription URL exists
        sub_url = user_data.get("remnawaveSubscriptionUrl")
        keyboard_json = None
        if sub_url:
            try:
                from vkbottle import Keyboard, OpenLink
                kb = Keyboard(inline=True)
                kb.add(OpenLink(label="🔗 Подключить", link=sub_url))
                keyboard_json = kb.get_json()
            except Exception as kb_err:
                logger.error(f"Failed to generate keyboard for user {user_uid}: {kb_err}")

        # 1. Send VK message
        msg_sent = await send_vk_message(
            vk_id,
            args.message,
            tokens,
            image_paths,
            keyboard=keyboard_json,
            dry_run=args.dry_run
        )
        if msg_sent:
            success_msg_count += 1
        else:
            fail_msg_count += 1

        # 2. Add days to subscription
        if not msg_sent and args.skip_msg_failures:
            logger.info(f"Skipping subscription extension for user {user_uid} because message failed to send.")
            skipped_db_count += 1
            continue

        new_ends_at = ends_at + timedelta(days=args.days)

        if not args.dry_run:
            try:
                # Update Firestore
                await asyncio.to_thread(
                    lambda: snap.reference.update({
                        "subscriptionEndsAt": new_ends_at,
                        "updatedAt": firestore.SERVER_TIMESTAMP,
                    })
                )
                
                # Update Remnawave
                try:
                    await _update_remnawave_subscription(user_uid, new_ends_at)
                    logger.info(f"Successfully extended subscription by +{args.days} days and synced to Remnawave for user {user_uid}.")
                except Exception as rw_err:
                    logger.error(f"Firestore updated, but failed to sync to Remnawave for user {user_uid}: {rw_err}")
                
                updated_db_count += 1
            except Exception as db_err:
                logger.error(f"Failed to update Firestore for user {user_uid}: {db_err}")
        else:
            logger.info(f"[Dry Run] Would extend subscription by +{args.days} days for user {user_uid}. (New expiry: {new_ends_at})")
            updated_db_count += 1

    # Print summary
    logger.info("=== Process Finished ===")
    logger.info(f"Total processed users: {processed_count}")
    logger.info(f"VK Messages sent successfully: {success_msg_count}")
    logger.info(f"VK Messages failed: {fail_msg_count}")
    logger.info(f"Subscriptions extended/updated: {updated_db_count}")
    logger.info(f"Subscriptions skipped: {skipped_db_count}")

if __name__ == "__main__":
    asyncio.run(main())
