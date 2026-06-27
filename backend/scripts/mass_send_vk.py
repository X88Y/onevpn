#!/usr/bin/env python3
"""Mass send a VK message with optional photo attachments."""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
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
backend_dir = script_dir.parent
bot_dir = backend_dir / "bot"
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
        description="Mass send a VK message to VK users."
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
            "Уважаемые пользователи🫶\n\n"
            "Hit VPN / Hit Wave подвергся блокировке РКН и в ближайшее время не будет работать!\n\n"
            "Для вашего удобства, что бы Вы всегда оставались на связи и с доступом в интернет сделали отдельный MVM VPN.\n\n"
            "Стоимость подписки поставили минимальную и в добавок 4 пробных дня.\n\n"
            "Что бы подключиться, воспользуйтесь инструкцией - https://vk.ru/clip-223445666_456239027\n\n"
            "❗️Также у нас на пару часов ломался сайт подключения «Ошибка 403 Forbiden» эту ошибку исправили, что бы ключ подключения обновился и сайт заработал, нажмите кнопку «Профиль» и в новом сообщение от бота все должно работать🙌\n\n"
            "Просим прощения за доставленные неудобства и в качестве извинений прикрепляем промокод на небольшую скидку : SORRY10\n\n"
            "Спасибо за понимание🫡"
        ),
        help="Message to send to VK users."
    )
    parser.add_argument(
        "--images",
        type=str,
        nargs="*",
        default=None,
        help="List of image paths to attach (defaults to scripts/media/prfile.jpg)."
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
        help="Unused compatibility flag (kept for backward-compatible CLI invocations)."
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help=(
            "Start of recipients activity window. "
            "ISO format, e.g. 2026-06-23T14:00:00 or 2026-06-23 14:00:00 "
            "(without timezone = local timezone). "
            "Default: yesterday at 14:00 local time."
        ),
    )
    parser.add_argument(
        "--until",
        type=str,
        default=None,
        help=(
            "End of recipients activity window in ISO format. "
            "Default: now."
        ),
    )
    parser.add_argument(
        "--sent-log",
        type=str,
        default=None,
        help="Path to append VK user IDs after successful send (default: scripts/sended_group_profile.txt).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose debug logs."
    )
    return parser.parse_args()


def _default_since_utc() -> datetime:
    now_local = datetime.now().astimezone()
    yesterday_local_date = (now_local - timedelta(days=1)).date()
    since_local = datetime.combine(
        yesterday_local_date,
        time(hour=14, minute=0, second=0),
        tzinfo=now_local.tzinfo,
    )
    return since_local.astimezone(timezone.utc)


def _parse_dt_arg(value: str, field_name: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(
            f"Invalid {field_name}: {value!r}. Use ISO format like 2026-06-23T14:00:00."
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt.astimezone(timezone.utc)


def _append_sent_user_id(log_path: Path, vk_id: str, user_uid: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"{vk_id}\t{user_uid}\n")

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
        # Default to scripts/media/prfile.jpg
        image_paths = [script_dir / "media" / "prfile.jpg"]

    # Resolve recipients activity window
    try:
        since_utc = _parse_dt_arg(args.since, "since") if args.since else _default_since_utc()
        until_utc = _parse_dt_arg(args.until, "until") if args.until else datetime.now(timezone.utc)
    except ValueError as dt_err:
        logger.error(str(dt_err))
        sys.exit(1)

    if since_utc >= until_utc:
        logger.error("Invalid time window: --since must be earlier than --until.")
        sys.exit(1)

    sent_log_path = Path(args.sent_log) if args.sent_log else script_dir / "sended_group_profile.txt"
    if not args.dry_run:
        logger.info("Successful sends will be appended to %s", sent_log_path)

    # Resolve env path
    env_path = args.env
    if env_path:
        target_env = Path(env_path)
    else:
        # Try bot/.env first, then server_manager/.env
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
        from mvm_bot.firebase_client import init_firebase
        from mvm_bot.datetime_utils import as_utc_datetime
        from mvm_bot.config import vk_bot_tokens
    except ImportError as e:
        logger.error(f"Failed to import dependencies: {e}. Are you inside the correct virtual environment?")
        sys.exit(1)

    tokens = vk_bot_tokens()
    if not tokens:
        logger.error("No VK_BOT_TOKENS or VK_BOT_TOKEN found in environment/env file.")
        sys.exit(1)
    logger.info(f"Loaded {len(tokens)} VK bot token(s).")
    logger.info(
        "Recipients activity window (UTC): %s -> %s",
        since_utc.isoformat(),
        until_utc.isoformat(),
    )

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
    matched_by_time_count = 0
    success_msg_count = 0
    fail_msg_count = 0

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

        # Filter recipients by last activity ("who wrote yesterday from 14:00")
        updated_at = as_utc_datetime(user_data.get("updatedAt"))
        if not updated_at:
            logger.info(f"Skipping user {user_uid}: no updatedAt timestamp.")
            continue
        if updated_at < since_utc or updated_at > until_utc:
            continue

        matched_by_time_count += 1
        processed_count += 1
        logger.info(
            f"[{processed_count}/{len(fb_snaps)}] Processing user {user_uid} "
            f"(VK ID: {vk_id}, updatedAt={updated_at.isoformat()})..."
        )

        # Build keyboard with "Профиль" button (same as bot welcome flow)
        keyboard_json = None
        try:
            from vkbottle import Keyboard, Text
            kb = Keyboard(one_time=False, inline=False)
            kb.add(Text("Профиль"))
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
            if not args.dry_run:
                _append_sent_user_id(sent_log_path, vk_id, user_uid)
        else:
            fail_msg_count += 1

    # Print summary
    logger.info("=== Process Finished ===")
    logger.info(f"Total processed users: {processed_count}")
    logger.info(f"Matched by activity window: {matched_by_time_count}")
    logger.info(f"VK Messages sent successfully: {success_msg_count}")
    logger.info(f"VK Messages failed: {fail_msg_count}")
    if not args.dry_run and success_msg_count:
        logger.info("Sent user IDs saved to %s", sent_log_path)

if __name__ == "__main__":
    asyncio.run(main())
