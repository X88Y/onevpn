import secrets
import uuid
from dataclasses import dataclass
from typing import Optional

from aiogram.types import User  # type: ignore[import-not-found]


def telegram_uid(tg_id: int) -> str:
    return f"tg:{tg_id}"


def vk_uid(vk_id: int) -> str:
    return f"vk:{vk_id}"


@dataclass
class VkProfile:
    id: int
    first_name: str
    last_name: Optional[str]
    screen_name: Optional[str]


def _display_name_vk(profile: VkProfile) -> str:
    full_name = " ".join(
        part for part in [profile.first_name, profile.last_name] if part
    )
    if full_name:
        return full_name
    if profile.screen_name:
        return profile.screen_name
    return f"VK user {profile.id}"


def generate_referral_code() -> str:
    return secrets.token_hex(4)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False

    return True


def _display_name(tg_user: User) -> str:
    full_name = " ".join(
        part for part in [tg_user.first_name, tg_user.last_name] if part
    )
    if full_name:
        return full_name

    if tg_user.username:
        return f"@{tg_user.username}"

    return f"Telegram user {tg_user.id}"


def _remnawave_username(user_uid: str) -> str:
    # Remnawave username max length is 36 characters.
    # A UUID is 36 chars including hyphens; with "mvm-" prefix it becomes 40.
    # Strip hyphens so it fits exactly: 4 + 32 = 36.
    return f"mvm-{user_uid.replace('-', '')}"
