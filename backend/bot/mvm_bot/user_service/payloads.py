from typing import Optional

from aiogram.types import User  # type: ignore[import-not-found]
from firebase_admin import auth, firestore  # type: ignore[import-not-found,import-untyped]

from mvm_bot.user_service.helpers import VkProfile, generate_referral_code, telegram_uid, vk_uid
from mvm_bot.user_service.trial import _initial_trial_fields, _missing_trial_defaults


def telegram_payload(
    uid: str,
    tg_user: User,
    auth_user: auth.UserRecord,
    exists: bool,
) -> dict:
    payload = {
        "uid": uid,
        "authUid": auth_user.uid,
        "tgId": str(tg_user.id),
        "username": tg_user.username,
        "firstName": tg_user.first_name,
        "lastName": tg_user.last_name,
        "languageCode": tg_user.language_code,
        "isBot": tg_user.is_bot,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if not exists:
        payload["createdAt"] = firestore.SERVER_TIMESTAMP
    return payload


def vk_users_mirror_payload(
    uid: str,
    profile: VkProfile,
    auth_user: auth.UserRecord,
    exists: bool,
    group_id: Optional[int] = None,
) -> dict:
    payload = {
        "uid": uid,
        "authUid": auth_user.uid,
        "vkId": str(profile.id),
        "screenName": profile.screen_name,
        "firstName": profile.first_name,
        "lastName": profile.last_name,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if group_id is not None:
        payload["vkGroupId"] = str(group_id)
        payload["vkGroupIds"] = firestore.ArrayUnion([str(group_id)])
    if not exists:
        payload["createdAt"] = firestore.SERVER_TIMESTAMP
    return payload


def users_payload(
    uid: str,
    tg_user: User,
    auth_user: auth.UserRecord,
    exists: bool,
    current_data: Optional[dict] = None,
    referral_code: Optional[str] = None,
) -> dict:
    del uid, auth_user
    current_data = current_data or {}
    payload = {
        "externalTg": telegram_uid(tg_user.id),
        "updatedAt": firestore.SERVER_TIMESTAMP,
        **_missing_trial_defaults(current_data),
    }
    if not current_data.get("referralCode"):
        payload["referralCode"] = generate_referral_code()
    if "renewalDaysBefore" not in current_data:
        payload["renewalDaysBefore"] = 3
    if not exists:
        payload.update(
            {
                **_initial_trial_fields(),
                "externalAppleId": None,
                "externalVk": None,
                "referredByCode": referral_code,
                "createdAt": firestore.SERVER_TIMESTAMP,
            }
        )
    return payload


def vk_users_document_payload(
    uid: str,
    profile: VkProfile,
    auth_user: auth.UserRecord,
    exists: bool,
    current_data: Optional[dict] = None,
    referral_code: Optional[str] = None,
    group_id: Optional[int] = None,
) -> dict:
    del uid, auth_user
    current_data = current_data or {}
    payload = {
        "externalVk": vk_uid(profile.id),
        "updatedAt": firestore.SERVER_TIMESTAMP,
        **_missing_trial_defaults(current_data),
    }
    if group_id is not None:
        payload["vkGroupId"] = str(group_id)
        payload["vkGroupIds"] = firestore.ArrayUnion([str(group_id)])
    if not current_data.get("referralCode"):
        payload["referralCode"] = generate_referral_code()
    if "renewalDaysBefore" not in current_data:
        payload["renewalDaysBefore"] = 3
    if not exists:
        payload.update(
            {
                **_initial_trial_fields(),
                "externalAppleId": None,
                "externalTg": None,
                "referredByCode": referral_code,
                "createdAt": firestore.SERVER_TIMESTAMP,
            }
        )
    return payload
