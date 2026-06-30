import hmac
import hashlib
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, firestore

from remnawave_webhook_server.config import (
    webhook_secret,
    service_account_path,
)
from remnawave_webhook_server.notifications import notify_tg_user, notify_vk_user
from remnawave_webhook_server.expiry_notifier import (
    handle_expiry_webhook_event,
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("remnawave_webhook_server")


app = FastAPI(title="Remnawave Webhook Server")


# Global DB client
db_client = None

def init_firebase():
    global db_client
    if db_client is not None:
        return db_client
    
    try:
        if not firebase_admin._apps:
            path = service_account_path()
            if path:
                logger.info(f"Initializing Firebase Admin with certificate: {path}")
                firebase_admin.initialize_app(credentials.Certificate(path))
            else:
                logger.info("Initializing Firebase Admin with default credentials")
                firebase_admin.initialize_app()
        db_client = firestore.client()
        return db_client
    except Exception as exc:
        logger.error(f"Failed to initialize Firebase Admin: {exc}")
        raise

class WebhookPayload(BaseModel):
    scope: str
    event: str
    timestamp: str
    data: Dict[str, Any]
    meta: Optional[Dict[str, Any]] = None

async def find_firestore_user(db, rw_uuid: str, username: str) -> Optional[dict]:
    # 1. Search by remnawaveUuid
    if rw_uuid:
        docs = await asyncio.to_thread(
            lambda: list(db.collection("users").where("remnawaveUuid", "==", rw_uuid).limit(1).get())
        )
        if docs:
            user_data = docs[0].to_dict()
            user_data["_doc_id"] = docs[0].id
            return user_data

    # 2. Search by document ID (parse from username if username starts with "mvm-")
    if username and username.startswith("mvm-"):
        clean_uid = username[4:]
        if len(clean_uid) == 32:
            reconstructed_uid = f"{clean_uid[:8]}-{clean_uid[8:12]}-{clean_uid[12:16]}-{clean_uid[16:20]}-{clean_uid[20:]}"
            doc = await asyncio.to_thread(
                lambda: db.collection("users").document(reconstructed_uid).get()
            )
            if doc.exists:
                user_data = doc.to_dict()
                user_data["_doc_id"] = doc.id
                return user_data
            
            doc_clean = await asyncio.to_thread(
                lambda: db.collection("users").document(clean_uid).get()
            )
            if doc_clean.exists:
                user_data = doc_clean.to_dict()
                user_data["_doc_id"] = doc_clean.id
                return user_data
    return None

async def process_user_event(payload: WebhookPayload):
    try:
        db = init_firebase()
        event_type = payload.event
        data = payload.data
        meta = payload.meta or {}

        rw_uuid = data.get("uuid") or data.get("id")
        username = data.get("username")
        
        user_data = await find_firestore_user(db, rw_uuid, username)
        if not user_data:
            logger.warning(f"No Firestore user found for Remnawave uuid={rw_uuid}, username={username}")
            return
            
        doc_id = user_data.get("_doc_id")
        logger.info(f"Processing event '{event_type}' for user {doc_id}")
        
        if event_type in (
            "user.expiration",
            "user.expired",
            "user.not_connected",
            "user.expires_in_72_hours",
            "user.expires_in_48_hours",
            "user.expires_in_24_hours",
            "user.expired_24_hours_ago",
        ):
            await handle_expiry_webhook_event(db, user_data, event_type, data, meta)
            return

    except Exception:
        logger.exception("Failed processing user webhook event background task")

@app.post("/webhook")
async def handle_webhook(request: Request):
    signature = request.headers.get("x-remnawave-signature")
    body_bytes = await request.body()
    
    secret = webhook_secret()
    if secret:
        if not signature:
            logger.warning("Missing x-remnawave-signature header")
            raise HTTPException(status_code=401, detail="Missing signature")
        
        computed_sig = hmac.new(
            key=secret.encode("utf-8"),
            msg=body_bytes,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(computed_sig, signature):
            logger.warning("Invalid x-remnawave-signature header")
            raise HTTPException(status_code=401, detail="Invalid signature")
            
    try:
        payload_dict = json.loads(body_bytes.decode("utf-8"))
        payload = WebhookPayload(**payload_dict)
    except Exception as exc:
        logger.error(f"Failed to parse payload: {exc}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    if payload.scope == "user":
        asyncio.create_task(process_user_event(payload))
        logger.info(f"Accepted event '{payload.event}' for scope 'user'")
    else:
        logger.info(f"Skipped event '{payload.event}' (unsupported scope '{payload.scope}')")
        
    return {"status": "accepted"}

@app.get("/health")
async def health():
    return {"status": "ok"}
