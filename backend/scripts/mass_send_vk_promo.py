#!/usr/bin/env python3
"""Mass send message to VK users who have their last message before 2025."""

import sys
import os
import argparse
import asyncio
import logging
import json
from datetime import datetime, timezone
from pathlib import Path
import aiohttp

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("mass_send_vk_promo")

DEFAULT_VK_TOKEN = ("vk1.a.J-qP_B4VFuvCb63pN3WsbtLHeQuMwULBtE1jjIYcSPCUbzPxTK40f4w0hRoQAz5Fde1suVTaxlJeif0Ik5tuqvLfrqIuNN9gzMVwbvePxL2qM7az43Q-K43jOjnFzPvxslhoQFEJd_TujzvKDG9CZMrdL6iWV-pTj5QseHIkS5DRIIJg1oSuK-bO6K1kEa-2QuNdiLTEuahjay5C7Oiuzg")

PROMO_MESSAGE = (
    "Хорошие новости❗️\n\n"
    "Если давно искали недорогой и стабильный впнчик без рекламы, мы как раз такой сделали…\n\n"
    "Даем 4 дня пробной версии, просто напиши любое сообщение и пользуйся🫶"
)

def parse_args():
    parser = argparse.ArgumentParser(
        description="Mass send a VK promo message to users whose last message was before 2025."
    )
    parser.add_argument(
        "--token",
        type=str,
        default=DEFAULT_VK_TOKEN,
        help="VK Access Token to use."
    )
    parser.add_argument(
        "--image",
        type=str,
        default="scripts/media/telegram-cloud-photo-size-2-5231021355237581058-y.jpg",
        help="Path to the image to upload and attach."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=2000,
        help="Limit the number of users to message (default: 2000)."
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.34,
        help="Delay in seconds between sending messages to respect VK rate limits (default: 0.34s)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run: fetch and show target users but do not send messages."
    )
    return parser.parse_args()

async def upload_photo(token: str, image_path: Path) -> str:
    """Uploads the photo using vkbottle and returns the attachment string."""
    from vkbottle import API
    from vkbottle.tools import PhotoMessageUploader

    logger.info(f"Uploading photo {image_path.name} to VK...")
    api = API(token)
    uploader = PhotoMessageUploader(api)
    
    attempts = 5
    for attempt in range(1, attempts + 1):
        try:
            attachment_str = await uploader.upload(file_source=str(image_path))
            logger.info(f"Successfully uploaded photo: {attachment_str}")
            return attachment_str
        except Exception as e:
            logger.error(f"Failed to upload photo (attempt {attempt}/{attempts}): {e}")
            if attempt < attempts:
                await asyncio.sleep(3)
    raise RuntimeError("Failed to upload photo after all attempts.")

async def fetch_inactive_vk_users(token: str, before_timestamp: int, limit: int = None) -> list[tuple[int, int]]:
    """
    Fetches peer IDs of inactive VK users from getConversations.
    Returns a list of tuples: (peer_id, last_message_timestamp).
    """
    inactive_users = []
    offset = 0
    count = 200
    
    async with aiohttp.ClientSession() as session:
        while True:
            params = {
                "access_token": token,
                "v": "5.231",
                "offset": offset,
                "count": count,
                "extended": 0
            }
            logger.info(f"Fetching conversations from VK API (offset={offset})...")
            
            try:
                async with session.post("https://api.vk.com/method/messages.getConversations", data=params) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error(f"HTTP error {resp.status} fetching conversations: {body}")
                        break
                    
                    data = await resp.json()
                    if "error" in data:
                        logger.error(f"VK API error: {data['error']}")
                        break
                    
                    response_obj = data.get("response", {})
                    items = response_obj.get("items", [])
                    if not items:
                        logger.info("No more conversations found.")
                        break
                    
                    for item in items:
                        conv = item.get("conversation", {})
                        peer = conv.get("peer", {})
                        peer_id = peer.get("id")
                        peer_type = peer.get("type")
                        
                        # Only target individual users (type == "user" and positive ID)
                        if peer_type != "user" or not peer_id or peer_id <= 0:
                            continue
                        
                        # Determine last message date
                        last_msg = item.get("last_message", {})
                        date = last_msg.get("date")
                        if not date:
                            date = conv.get("last_conversation_activity_date")
                        
                        if date and date < before_timestamp:
                            inactive_users.append((peer_id, date))
                            if limit and len(inactive_users) >= limit:
                                break
                        print(date)
                    
                    logger.info(f"Fetched {len(items)} items. Total inactive so far: {len(inactive_users)}")
                    
                    if limit and len(inactive_users) >= limit:
                        break
                    
                    if len(items) < count:
                        break
            except Exception as e:
                logger.error(f"Network exception while fetching conversations: {e}")
                break
                
            offset += count
            await asyncio.sleep(0.34)  # Avoid rate limiting
            
    return inactive_users

async def send_vk_message(
    session: aiohttp.ClientSession,
    token: str,
    peer_id: int,
    message: str,
    keyboard_json: str,
    attachment: str = None
) -> bool:
    params = {
        "peer_id": peer_id,
        "message": message,
        "random_id": str(int(datetime.now(timezone.utc).timestamp() * 1000) + peer_id % 1000),
        "access_token": token,
        "v": "5.231",
        "keyboard": keyboard_json
    }
    if attachment:
        params["attachment"] = attachment
    try:
        async with session.post("https://api.vk.com/method/messages.send", data=params) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.error(f"HTTP error {resp.status} sending to {peer_id}: {body}")
                return False
            data = await resp.json()
            if "error" in data:
                logger.error(f"VK API error sending to {peer_id}: {data['error']}")
                return False
            return True
    except Exception as e:
        logger.error(f"Exception sending to {peer_id}: {e}")
        return False

async def main():
    args = parse_args()
    
    # 2025-01-01 00:00:00 UTC
    before_timestamp = 1735689600
    before_date_str = datetime.fromtimestamp(before_timestamp, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    # Resolve image path
    image_path = Path(args.image)
    if not image_path.is_absolute():
        backend_root = Path(__file__).resolve().parents[1]
        candidate1 = Path.cwd() / args.image
        candidate2 = backend_root / args.image
        if candidate1.exists():
            image_path = candidate1
        elif candidate2.exists():
            image_path = candidate2
            
    if not image_path.exists():
        logger.error(f"Image path {image_path} does not exist. Exiting.")
        sys.exit(1)
        
    logger.info(f"Starting VK mass send for users with last message before {before_date_str}")
    logger.info(f"Target image for promo: {image_path}")
    
    inactive_users = await fetch_inactive_vk_users(args.token, before_timestamp, limit=args.limit)
    logger.info(f"Found {len(inactive_users)} users matching criteria.")
    
    if not inactive_users:
        logger.info("No inactive users found. Exiting.")
        return
        
    if args.limit:
        inactive_users = inactive_users[:args.limit]
        logger.info(f"Limited to first {args.limit} users.")
        
    # Build keyboard under the input field
    keyboard = {
        "inline": False,
        "buttons": [
            [
                {
                    "action": {
                        "type": "text",
                        "label": "Получить VPN",
                        "payload": ""
                    },
                    "color": "primary"
                }
            ]
        ]
    }
    keyboard_json = json.dumps(keyboard)
    
    attachment_str = None
    if not args.dry_run:
        try:
            attachment_str = await upload_photo(args.token, image_path)
        except Exception as e:
            logger.error(f"Image upload failed: {e}. Exiting.")
            sys.exit(1)
    else:
        logger.info(f"[Dry Run] Would upload image: {image_path}")
    
    if args.dry_run:
        logger.info("=== DRY RUN MODE ===")
        for peer_id, last_date in inactive_users:
            last_date_str = datetime.fromtimestamp(last_date, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            logger.info(f"[Dry Run] Would send to user {peer_id} (Last message: {last_date_str}) with attachment {attachment_str}")
        logger.info(f"Dry run finished. Would send message to {len(inactive_users)} users.")
        return
        
    logger.info(f"Starting actual send to {len(inactive_users)} users...")
    success_count = 0
    fail_count = 0
    
    async with aiohttp.ClientSession() as session:
        for idx, (peer_id, last_date) in enumerate(inactive_users, 1):
            last_date_str = datetime.fromtimestamp(last_date, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            logger.info(f"[{idx}/{len(inactive_users)}] Sending to user {peer_id} (Last message: {last_date_str})...")
            
            success = await send_vk_message(session, args.token, peer_id, PROMO_MESSAGE, keyboard_json, attachment_str)
            if success:
                success_count += 1
                logger.info(f"Successfully sent to user {peer_id}")
            else:
                fail_count += 1
                logger.warning(f"Failed to send to user {peer_id}")
                
            await asyncio.sleep(args.delay)
            
    logger.info("=== MASS SEND COMPLETED ===")
    logger.info(f"Total processed: {len(inactive_users)}")
    logger.info(f"Successfully sent: {success_count}")
    logger.info(f"Failed: {fail_count}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Exiting.")
        sys.exit(0)
