#!/usr/bin/env python3
"""Broadcast a VK message to all users who chatted with each community bot.

Tokens are loaded from Firestore (vk_tokens collection).
Progress is saved to scripts/sended/{group_id}.txt after each successful send.

Example — users who texted between 02:00 and 11:00 Moscow time (UTC+3):

    python3 vk_broadcast.py \\
        --since "2026-06-29T02:00:00+03:00" \\
        --until "2026-06-29T11:00:00+03:00"
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
BOT_DIR = BACKEND_DIR / "bot"
if not BOT_DIR.is_dir():
    if (SCRIPT_DIR / "mvm_bot").is_dir():
        BOT_DIR = SCRIPT_DIR
    else:
        raise RuntimeError("Cannot find bot/ directory")

sys.path.insert(0, str(BOT_DIR))

MESSAGE = """\
Если Вы оплатили подписку, но она не активировалась или не продлилась - это сообщение для вас❗️

Ночью мы обновляли систему и не заметили этого бага, очень сильно извиняемся перед всеми, кто не мог подключиться все это время🙏

Сейчас все починили, нажмите кнопку «Профиль» она находится снизу, подписка обновится и сможете спокойно подключиться по новой🥰

Инструкция подключения - https://vk.ru/clip-223445666_456239020

В качестве извинений за неудобства, прикрепляем промокод на скидку 20% — SUBOFF20

Спасибо за ваше терпение и понимание🫶"""

ASSETS_DIR = SCRIPT_DIR / "assetss"
SENDED_DIR = SCRIPT_DIR / "sended"
VK_API_VERSION = "5.231"
SEND_DELAY_SEC = 0.34
PAGE_SIZE = 200
DEFAULT_IMAGE_NAMES = ("photo_1.jpg", "photo_2.jpg")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("vk_broadcast")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Broadcast a VK message to all conversation peers.",
        epilog=(
            "Example (02:00–11:00 MSK, UTC+3):\n"
            "  python3 vk_broadcast.py "
            '--since "2026-06-29T02:00:00+03:00" '
            '--until "2026-06-29T11:00:00+03:00"'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="Path to .env file (defaults to bot/.env).",
    )
    parser.add_argument(
        "--message",
        type=str,
        default=MESSAGE,
        help="Message text to send.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send messages or update sended files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max successful sends per group token.",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Send only with this VK bot token (otherwise all active tokens from DB).",
    )
    parser.add_argument(
        "--images",
        type=str,
        nargs="*",
        default=None,
        help=(
            "Image paths to attach (default: scripts/assetss/photo_1.jpg and photo_2.jpg). "
            "Pass none with --no-images."
        ),
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Send text only, without photo attachments.",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help=(
            "Include only users who texted the bot on or after this time. "
            "ISO format, e.g. 2026-06-29T02:00:00+03:00 for MSK (UTC+3)."
        ),
    )
    parser.add_argument(
        "--until",
        type=str,
        default=None,
        help=(
            "Include only users who texted the bot on or before this time. "
            "ISO format, e.g. 2026-06-29T11:00:00+03:00 for MSK (UTC+3). "
            "Default with --since: now."
        ),
    )
    return parser.parse_args()


def parse_dt_arg(value: str, field_name: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(
            f"Invalid {field_name}: {value!r}. Use ISO format like 2026-06-28T22:00:00."
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt.astimezone(timezone.utc)


def resolve_time_window(args: argparse.Namespace) -> tuple[datetime | None, datetime | None]:
    if not args.since and not args.until:
        return None, None
    try:
        since_utc = parse_dt_arg(args.since, "since") if args.since else None
        until_utc = (
            parse_dt_arg(args.until, "until")
            if args.until
            else datetime.now(timezone.utc)
        )
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    if since_utc and until_utc and since_utc >= until_utc:
        logger.error("Invalid time window: --since must be earlier than --until.")
        sys.exit(1)
    return since_utc, until_utc


def message_timestamp_to_dt(date_ts: object) -> datetime | None:
    if isinstance(date_ts, (int, float)):
        return datetime.fromtimestamp(int(date_ts), tz=timezone.utc)
    return None


def is_incoming_user_message(msg: dict) -> bool:
    return msg.get("out") in (0, False)


def dt_in_window(
    msg_dt: datetime,
    since_utc: datetime | None,
    until_utc: datetime | None,
) -> bool:
    if since_utc is not None and msg_dt < since_utc:
        return False
    if until_utc is not None and msg_dt > until_utc:
        return False
    return True


async def fetch_last_user_message_dt(
    session: aiohttp.ClientSession,
    token: str,
    peer_id: int,
    cache: dict[int, datetime | None],
    group_logger: logging.Logger,
) -> datetime | None:
    if peer_id in cache:
        return cache[peer_id]

    data: dict | None = None
    for attempt in range(5):
        data = await vk_api_post(
            session,
            "messages.getHistory",
            token,
            {"peer_id": peer_id, "count": 200, "rev": 1},
        )
        if data is None:
            cache[peer_id] = None
            return None
        if "error" not in data:
            break
        err = data["error"]
        if err.get("error_code") == 9 and attempt < 4:
            await asyncio.sleep(5 * (attempt + 1))
            continue
        group_logger.debug("messages.getHistory failed for %s: %s", peer_id, err)
        cache[peer_id] = None
        return None

    user_dt: datetime | None = None
    for msg in data.get("response", {}).get("items", []):
        if is_incoming_user_message(msg):
            user_dt = message_timestamp_to_dt(msg.get("date"))
            break

    cache[peer_id] = user_dt
    await asyncio.sleep(0.05)
    return user_dt


async def user_texted_in_window(
    session: aiohttp.ClientSession,
    token: str,
    peer_id: int,
    item: dict,
    since_utc: datetime | None,
    until_utc: datetime | None,
    cache: dict[int, datetime | None],
    group_logger: logging.Logger,
) -> bool:
    if since_utc is None and until_utc is None:
        return True

    last_message = item.get("last_message") or {}
    last_dt = message_timestamp_to_dt(last_message.get("date"))
    if last_dt is None:
        return False

    # if is_incoming_user_message(last_message):
    return dt_in_window(last_dt, since_utc, until_utc)

    # Bot replied last — last_message.date is not when the user wrote.
    if since_utc is not None and last_dt < since_utc:
        return False

    user_dt = await fetch_last_user_message_dt(
        session,
        token,
        peer_id,
        cache,
        group_logger,
    )
    if user_dt is None:
        return False
    return dt_in_window(user_dt, since_utc, until_utc)


def resolve_image_paths(args: argparse.Namespace) -> list[Path]:
    if args.no_images:
        return []
    if args.images is not None:
        return [Path(p).expanduser() for p in args.images]
    return [ASSETS_DIR / name for name in DEFAULT_IMAGE_NAMES]


def load_env(env_path: str | None) -> None:
    candidates = []
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.extend([BOT_DIR / ".env", BACKEND_DIR / "server_manager" / ".env"])
    for path in candidates:
        if path.exists():
            load_dotenv(path)
            logger.info("Loaded .env from %s", path)
            return
    logger.warning("No .env file found, relying on existing environment variables")


def load_sent_ids(sended_file: Path, group_logger: logging.Logger) -> set[int]:
    sent_ids: set[int] = set()
    if not sended_file.exists():
        return sent_ids
    try:
        for line in sended_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                sent_ids.add(int(line.split()[0]))
            except ValueError:
                group_logger.warning("Skipping invalid line in %s: %s", sended_file.name, line)
    except OSError as exc:
        group_logger.error("Error reading %s: %s", sended_file.name, exc)
    return sent_ids


def append_sent_id(sended_file: Path, peer_id: int) -> None:
    sended_file.parent.mkdir(parents=True, exist_ok=True)
    with sended_file.open("a", encoding="utf-8") as file:
        file.write(f"{peer_id}\n")


async def vk_api_post(
    session: aiohttp.ClientSession,
    method: str,
    token: str,
    params: dict,
) -> dict | None:
    payload = {"access_token": token, "v": VK_API_VERSION, **params}
    async with session.post(f"https://api.vk.com/method/{method}", data=payload) as resp:
        if resp.status != 200:
            body = await resp.text()
            logger.error("HTTP %s for %s: %s", resp.status, method, body)
            return None
        data = await resp.json()
        if "error" in data:
            return data
        return data


async def get_group_info(session: aiohttp.ClientSession, token: str) -> dict | None:
    data = await vk_api_post(session, "groups.getById", token, {})
    if not data or "error" in data:
        if data and "error" in data:
            logger.error("groups.getById error: %s", data["error"])
        return None
    groups = data.get("response", {}).get("groups", [])
    return groups[0] if groups else None


async def get_or_upload_attachments(
    token: str,
    image_paths: list[Path],
    group_logger: logging.Logger,
) -> str | None:
    existing = [path for path in image_paths if path.exists()]
    if not existing:
        group_logger.warning("No image files found to upload.")
        return None

    keys = [path.name for path in existing]
    try:
        from mvm_bot.firebase_client import get_vk_cached_attachment, set_vk_cached_attachment

        cached = await get_vk_cached_attachment(token, keys)
        if cached:
            group_logger.info("Using cached VK attachment for token %s: %s", token[:8], cached)
            return cached
    except Exception:
        group_logger.exception("Failed to read VK attachment cache from Firestore")

    from vkbottle import API
    from vkbottle.tools import PhotoMessageUploader

    api = API(token)
    uploader = PhotoMessageUploader(api)
    uploaded: list[str] = []

    for path in existing:
        for attempt in range(1, 6):
            try:
                group_logger.info(
                    "Uploading %s for token %s (attempt %s/5)...",
                    path.name,
                    token[:8],
                    attempt,
                )
                attachment_str = await uploader.upload(file_source=str(path))
                uploaded.append(attachment_str)
                break
            except Exception as exc:
                group_logger.error(
                    "Upload failed for %s (attempt %s/5): %s",
                    path.name,
                    attempt,
                    exc,
                )
                if attempt < 5:
                    await asyncio.sleep(3)

    if not uploaded:
        return None

    attachment = ",".join(uploaded)
    try:
        from mvm_bot.firebase_client import set_vk_cached_attachment

        await set_vk_cached_attachment(token, keys, attachment)
        group_logger.info("Saved VK attachment cache for token %s", token[:8])
    except Exception:
        group_logger.exception("Failed to save VK attachment cache to Firestore")

    return attachment


async def send_vk_message(
    session: aiohttp.ClientSession,
    token: str,
    peer_id: int,
    message: str,
    group_logger: logging.Logger,
    *,
    attachment: str | None = None,
) -> bool:
    params = {
        "peer_id": peer_id,
        "message": message,
        "random_id": str(int(datetime.now(timezone.utc).timestamp() * 1000) + peer_id % 1000),
    }
    if attachment:
        params["attachment"] = attachment
    for attempt in range(5):
        data = await vk_api_post(session, "messages.send", token, params)
        if data is None:
            return False
        if "error" not in data:
            return True
        err = data["error"]
        if err.get("error_code") == 9 and attempt < 4:
            wait = 5 * (attempt + 1)
            group_logger.warning(
                "Flood control sending to %s, sleeping %ss (attempt %s/5)",
                peer_id,
                wait,
                attempt + 1,
            )
            await asyncio.sleep(wait)
            continue
        group_logger.error(
            "VK API error sending to %s: %s (code %s)",
            peer_id,
            err.get("error_msg"),
            err.get("error_code"),
        )
        return False
    return False


async def process_group_mailing(
    token: str,
    session: aiohttp.ClientSession,
    *,
    message: str,
    image_paths: list[Path],
    dry_run: bool,
    limit: int | None,
    since_utc: datetime | None,
    until_utc: datetime | None,
) -> None:
    group_info = await get_group_info(session, token)
    if not group_info:
        logger.error("Could not resolve group for token %s... Skipping.", token[:10])
        return

    group_id = group_info["id"]
    group_name = group_info.get("name", f"Group {group_id}")
    group_logger = logging.getLogger(f"Group-{group_id}")
    group_logger.info("Starting mailing for group '%s' (%s)", group_name, group_id)

    sended_file = SENDED_DIR / f"{group_id}.txt"
    sent_ids = load_sent_ids(sended_file, group_logger)
    group_logger.info("Loaded %s already sent user IDs from %s", len(sent_ids), sended_file.name)
    if since_utc or until_utc:
        group_logger.info(
            "Time filter (UTC): since=%s until=%s (last user message; history lookup when bot replied last)",
            since_utc.isoformat() if since_utc else "any",
            until_utc.isoformat() if until_utc else "any",
        )

    attachment: str | None = None
    if image_paths:
        missing = [path for path in image_paths if not path.exists()]
        for path in missing:
            group_logger.warning("Image not found: %s", path)
        if dry_run:
            names = [path.name for path in image_paths if path.exists()]
            group_logger.info("[dry-run] Would attach images: %s", names or "none")
        else:
            attachment = await get_or_upload_attachments(token, image_paths, group_logger)
            if attachment:
                group_logger.info("Pre-uploaded attachment: %s", attachment)
            else:
                group_logger.warning("Proceeding without photo attachment.")

    success_count = 0
    fail_count = 0
    skipped_count = 0
    time_skipped_count = 0
    sent_this_run = 0
    offset = 0
    user_text_cache: dict[int, datetime | None] = {}

    while True:
        if limit is not None and sent_this_run >= limit:
            group_logger.info("Reached limit of %s sends for this group.", limit)
            break

        group_logger.info("Fetching conversations (offset=%s)...", offset)
        data = await vk_api_post(
            session,
            "messages.getConversations",
            token,
            {"offset": offset, "count": PAGE_SIZE, "extended": 0},
        )
        if data is None or "error" in data:
            if data and "error" in data:
                group_logger.error("messages.getConversations error: %s", data["error"])
            break

        items = data.get("response", {}).get("items", [])
        if not items:
            group_logger.info("No more conversations.")
            break

        page_users: list[int] = []
        page_time_skipped = 0
        for item in items:
            peer = item.get("conversation", {}).get("peer", {})
            if peer.get("type") != "user":
                continue
            peer_id = peer.get("id")
            if not isinstance(peer_id, int) or peer_id <= 0:
                continue
            if not await user_texted_in_window(
                session,
                token,
                peer_id,
                item,
                since_utc,
                until_utc,
                user_text_cache,
                group_logger,
            ):
                time_skipped_count += 1
                page_time_skipped += 1
                continue
            page_users.append(peer_id)

        if since_utc or until_utc:
            group_logger.info(
                "Page: %s user(s) match time filter, %s skipped",
                len(page_users),
                page_time_skipped,
            )

        for peer_id in page_users:
            if limit is not None and sent_this_run >= limit:
                break

            if peer_id in sent_ids:
                skipped_count += 1
                continue

            if dry_run:
                group_logger.info("[dry-run] Would send to user %s", peer_id)
                success_count += 1
                sent_this_run += 1
                sent_ids.add(peer_id)
                continue

            group_logger.info("Sending to user %s...", peer_id)
            success = await send_vk_message(
                session,
                token,
                peer_id,
                message,
                group_logger,
                attachment=attachment,
            )
            if success:
                append_sent_id(sended_file, peer_id)
                sent_ids.add(peer_id)
                success_count += 1
                sent_this_run += 1
            else:
                fail_count += 1

            await asyncio.sleep(SEND_DELAY_SEC)

        if len(items) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        await asyncio.sleep(SEND_DELAY_SEC)

    group_logger.info(
        "Finished. Sent: %s, failed: %s, skipped (already sent): %s, skipped (time filter): %s",
        success_count,
        fail_count,
        skipped_count,
        time_skipped_count,
    )


async def main() -> None:
    args = parse_args()
    load_env(args.env)

    if args.dry_run:
        logger.info("=== DRY RUN MODE ===")

    from mvm_bot.firebase_client import get_vk_tokens_from_db

    if args.token:
        tokens = [args.token.strip()]
    else:
        tokens = get_vk_tokens_from_db()

    if not tokens:
        logger.error("No active VK tokens found in Firestore.")
        sys.exit(1)

    since_utc, until_utc = resolve_time_window(args)
    if since_utc or until_utc:
        logger.info(
            "Recipients filter (UTC): since=%s until=%s",
            since_utc.isoformat() if since_utc else "any",
            until_utc.isoformat() if until_utc else "any",
        )

    image_paths = resolve_image_paths(args)
    if image_paths:
        logger.info(
            "Photo attachments: %s",
            ", ".join(str(path) for path in image_paths),
        )
    else:
        logger.info("No photo attachments.")

    logger.info("Found %s VK token(s) to process.", len(tokens))
    SENDED_DIR.mkdir(parents=True, exist_ok=True)

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(
            *[
                process_group_mailing(
                    token,
                    session,
                    message=args.message,
                    image_paths=image_paths,
                    dry_run=args.dry_run,
                    limit=args.limit,
                    since_utc=since_utc,
                    until_utc=until_utc,
                )
                for token in tokens
            ]
        )

    logger.info("All group mailings completed.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted.")
        sys.exit(0)
