from aiogram.types import User  # type: ignore[import-not-found]
from firebase_admin import auth  # type: ignore[import-not-found,import-untyped]

from mvm_bot.user_service.helpers import VkProfile, _display_name, _display_name_vk


def ensure_auth_user(uid: str, tg_user: User) -> auth.UserRecord:
    try:
        user = auth.get_user(uid)
    except auth.UserNotFoundError:
        user = auth.create_user(
            uid=uid,
            display_name=_display_name(tg_user),
        )

    auth.set_custom_user_claims(
        uid,
        {
            "provider": "telegram",
            "tgId": str(tg_user.id),
        },
    )
    return user


def ensure_vk_auth_user(uid: str, profile: VkProfile) -> auth.UserRecord:
    try:
        user = auth.get_user(uid)
    except auth.UserNotFoundError:
        user = auth.create_user(
            uid=uid,
            display_name=_display_name_vk(profile),
        )

    auth.set_custom_user_claims(
        uid,
        {
            "provider": "vk",
            "vkId": str(profile.id),
        },
    )
    return user
