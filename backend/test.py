import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Discover bot directory and load .env BEFORE any imports that read env vars
# ---------------------------------------------------------------------------
_script_dir = Path(__file__).resolve().parent

# Try to locate the bot/ folder (works whether this file lives in backend/ or backend/bot/)
if (_script_dir / "bot" / "mvm_bot").is_dir():
    BOT_DIR = _script_dir / "bot"
elif (_script_dir / "mvm_bot").is_dir():
    BOT_DIR = _script_dir
else:
    raise RuntimeError(
        "Cannot find bot/ directory. Place this file in backend/ or backend/bot/"
    )

sys.path.insert(0, str(BOT_DIR))

from dotenv import load_dotenv

_env_path = BOT_DIR / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
    print(f"Loaded .env from {_env_path}")
else:
    print(f"Warning: {_env_path} not found, relying on existing environment variables")

# ---------------------------------------------------------------------------
# 2. Imports (safe now that .env is loaded)
# ---------------------------------------------------------------------------
import asyncio
import logging
import os
import random
from datetime import datetime, timedelta

from vkbottle import API, Keyboard, OpenLink

from mvm_bot.user_service import VkProfile, extend_subscription_vk
from mvm_bot.constants import VK_SUPPORT_URL

VK_BOT_TOKEN = (
    os.getenv("VK_BOT_TOKEN")
    or "vk1.a.xiQBLVtxpiDUJ7YpezJ_dmdv3cK1DjKGDqWTfabHUBsLKFWPr_6u-9Jeow1Hp289GOcejd53dMxgk98DgpdZJFbxX6i5BeeHyyEso-PwTDAYZf9s1F06j3EC8YWbrKE3-BkB6BkZ-6ne5ONmiFsFl02ds0iRrGGZZzP5lDomkic9aqvrBZTnuzXhwAujKKSsNr6SoZTPj7fMh4vq5ocDqg"
)

vk = API(token=VK_BOT_TOKEN)
all_users_vk = set()


async def all_who_text_dm_less_than_week():
    messages = await vk.messages.get_conversations(filter="all", count=200)
    for item in messages.items:
        last_message = item.last_message
        if last_message and last_message.text and last_message.date:
            message_date = datetime.fromtimestamp(last_message.date)
            if datetime.now() - message_date < timedelta(days=7):
                # Only add real user peer IDs (not chats)
                if last_message.peer_id < 2000000000:
                    all_users_vk.add(last_message.peer_id)


async def process_users():
    await all_who_text_dm_less_than_week()
    print(f"Found {len(all_users_vk)} users who messaged in the last 4 days")

    if not all_users_vk:
        print("No users to process")
        return

    # Get user profiles from VK
    user_ids = list(all_users_vk)
    profiles_data = await vk.users.get(user_ids=user_ids)

    for profile_info in profiles_data:
        vk_id = profile_info.id
        profile = VkProfile(
            id=vk_id,
            first_name=profile_info.first_name,
            last_name=getattr(profile_info, "last_name", None),
            screen_name=getattr(profile_info, "screen_name", None),
        )

        try:
            # Ensure account exists and extend subscription by 4 days
            uid, data = await extend_subscription_vk(profile, days=4)

            sub_url = data.get("remnawaveSubscriptionUrl") or ""

            # Build keyboard with connection and support links
            kb = Keyboard(inline=True)
            kb.add(OpenLink(label="🔗 Подключить", link=sub_url))
            kb.row()
            kb.add(OpenLink(label="💬 Поддержка", link=VK_SUPPORT_URL))

            # Send apology + compensation message
            message_text = (
                "🙏 Приносим извинения за недавние неудобства!\n\n"
                "В качестве компенсации мы начислили вам +4 дня бесплатного использования VPN.\n\n"
                "Надеемся, что сервис снова работает стабильно. "
                "Если остались вопросы — обращайтесь в поддержку, мы всегда на связи! 💙"
            )

            await vk.messages.send(
                peer_id=vk_id,
                message=message_text,
                keyboard=kb.get_json(),
                random_id=random.randint(-2147483648, 2147483647),
            )
            print(f"✅ Processed VK user {vk_id}")

        except Exception as e:
            print(f"❌ Failed to process VK user {vk_id}: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Processing VK users from the last 4 days...")
    asyncio.run(process_users())
