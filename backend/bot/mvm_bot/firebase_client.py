import asyncio
import hashlib
import logging

import firebase_admin  # type: ignore[import-not-found,import-untyped]
from firebase_admin import credentials, firestore  # type: ignore[import-not-found,import-untyped]

from mvm_bot.config import service_account_path

logger = logging.getLogger(__name__)


def init_firebase() -> firestore.Client:
    if not firebase_admin._apps:
        account_path = service_account_path()
        if account_path is not None:
            firebase_admin.initialize_app(credentials.Certificate(account_path))
        else:
            firebase_admin.initialize_app()

    return firestore.client()


def _get_vk_cache_doc_id(token: str, keys: list[str]) -> str:
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    keys_str = ",".join(sorted(keys))
    keys_hash = hashlib.sha256(keys_str.encode('utf-8')).hexdigest()
    return f"{token_hash}_{keys_hash}"


async def get_vk_cached_attachment(token: str, keys: list[str]) -> str | None:
    db = init_firebase()
    doc_id = _get_vk_cache_doc_id(token, keys)
    try:
        doc_ref = db.collection("vk_attachments_cache").document(doc_id)
        doc = await asyncio.to_thread(doc_ref.get)
        if doc.exists:
            return doc.to_dict().get("attachment_str")
    except Exception:
        logger.exception(f"Failed to read from vk_attachments_cache for {doc_id}")
    return None


async def set_vk_cached_attachment(token: str, keys: list[str], attachment_str: str) -> None:
    db = init_firebase()
    doc_id = _get_vk_cache_doc_id(token, keys)
    try:
        doc_ref = db.collection("vk_attachments_cache").document(doc_id)
        await asyncio.to_thread(
            lambda: doc_ref.set({
                "attachment_str": attachment_str,
                "keys": keys,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
        )
    except Exception:
        logger.exception(f"Failed to write to vk_attachments_cache for {doc_id}")


def _get_tg_cache_doc_id(token: str, keys: list[str]) -> str:
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    keys_str = ",".join(sorted(keys))
    keys_hash = hashlib.sha256(keys_str.encode('utf-8')).hexdigest()
    return f"{token_hash}_{keys_hash}"


async def get_tg_cached_attachment(token: str, keys: list[str]) -> str | None:
    db = init_firebase()
    doc_id = _get_tg_cache_doc_id(token, keys)
    try:
        doc_ref = db.collection("tg_attachments_cache").document(doc_id)
        doc = await asyncio.to_thread(doc_ref.get)
        if doc.exists:
            return doc.to_dict().get("file_id")
    except Exception:
        logger.exception(f"Failed to read from tg_attachments_cache for {doc_id}")
    return None


async def set_tg_cached_attachment(token: str, keys: list[str], file_id: str) -> None:
    db = init_firebase()
    doc_id = _get_tg_cache_doc_id(token, keys)
    try:
        doc_ref = db.collection("tg_attachments_cache").document(doc_id)
        await asyncio.to_thread(
            lambda: doc_ref.set({
                "file_id": file_id,
                "keys": keys,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
        )
    except Exception:
        logger.exception(f"Failed to write to tg_attachments_cache for {doc_id}")


def get_vk_token_configs_from_db() -> list[dict]:
    db = init_firebase()
    try:
        docs = db.collection("vk_tokens").stream()
        configs = []
        for doc in docs:
            data = doc.to_dict()
            if data.get("status") != "inactive" and "token" in data:
                configs.append(data)
        return configs
    except Exception:
        logger.exception("Failed to get VK token configs from Firestore")
        return []


def get_vk_tokens_from_db() -> list[str]:
    return [config["token"] for config in get_vk_token_configs_from_db()]


def get_vk_token_config(token: str) -> dict | None:
    db = init_firebase()
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    try:
        doc_ref = db.collection("vk_tokens").document(token_hash)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
    except Exception:
        logger.exception(f"Failed to get VK token config for {token[:8]}")
    return None


def store_vk_token_in_db(token: str) -> None:
    db = init_firebase()
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    try:
        doc_ref = db.collection("vk_tokens").document(token_hash)
        doc = doc_ref.get()
        if not doc.exists:
            doc_ref.set({
                "token": token,
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "start_identifier": None,
                "status": "active"
            })
    except Exception:
        logger.exception(f"Failed to store VK token {token[:8]} in Firestore")


def update_vk_token_start_identifier(token: str, start_identifier: str | None) -> None:
    db = init_firebase()
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    try:
        doc_ref = db.collection("vk_tokens").document(token_hash)
        doc_ref.update({
            "start_identifier": start_identifier,
            "updated_at": firestore.SERVER_TIMESTAMP
        })
    except Exception:
        logger.exception(f"Failed to update start identifier for VK token {token[:8]}")


def update_vk_token_group_id(token: str, group_id: int) -> None:
    db = init_firebase()
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    try:
        doc_ref = db.collection("vk_tokens").document(token_hash)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            if not data.get("group_id"):
                doc_ref.update({
                    "group_id": group_id,
                    "updated_at": firestore.SERVER_TIMESTAMP
                })
                logger.info(f"Saved VK group_id {group_id} to Firestore for token {token[:8]}")
    except Exception:
        logger.exception(f"Failed to update group_id for VK token {token[:8]}")


def update_vk_token_webhook_setuped(token: str, webhook_setuped: bool, webhook_server_id: int | None = None) -> None:
    db = init_firebase()
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    try:
        doc_ref = db.collection("vk_tokens").document(token_hash)
        updates = {
            "webhook_setuped": webhook_setuped,
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        if webhook_server_id is not None:
            updates["webhook_server_id"] = webhook_server_id
        doc_ref.update(updates)
        logger.info(f"Updated VK token {token[:8]} webhook_setuped={webhook_setuped}")
    except Exception:
        logger.exception(f"Failed to update webhook_setuped for VK token {token[:8]}")


def get_vk_tokens_for_user(user_id: str) -> list[str]:
    db = init_firebase()
    try:
        users_ref = db.collection("users")
        external_candidates = [f"vk:{user_id}", str(user_id)]
        
        # Query by externalVk matching candidates
        user_docs = list(users_ref.where("externalVk", "in", external_candidates).limit(1).get())
        
        group_ids = set()
        user_data = None
        if user_docs:
            user_data = user_docs[0].to_dict() or {}
        else:
            doc = users_ref.document(user_id).get()
            if doc.exists:
                user_data = doc.to_dict() or {}
                
        if user_data:
            vk_group_ids = user_data.get("vkGroupIds")
            if isinstance(vk_group_ids, list):
                for gid in vk_group_ids:
                    if gid is not None:
                        group_ids.add(str(gid).strip())
            vk_group_id = user_data.get("vkGroupId")
            if vk_group_id is not None:
                group_ids.add(str(vk_group_id).strip())
                
        if not group_ids:
            logger.warning("No group IDs found for VK user %s", user_id)
            return []
            
        docs = db.collection("vk_tokens").get()
        tokens = []
        for doc in docs:
            data = doc.to_dict()
            if data.get("status") != "inactive" and "token" in data:
                token = data["token"].strip()
                g_id = data.get("group_id")
                if g_id is not None and str(g_id).strip() in group_ids:
                    tokens.append(token)
        return tokens
    except Exception:
        logger.exception("Failed to get VK tokens for user %s from Firestore", user_id)
        return []



