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
