import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import random
from fastapi import APIRouter, Depends, HTTPException, status
from firebase_admin import firestore

from server_manager.auth import require_api_key
from server_manager.config import settings
from server_manager.firestore_client import (
    VPN_CLIENTS_COLLECTION,
    VPN_SERVERS_COLLECTION,
    init_firestore,
)
from server_manager.models import (
    ProvisionRequest,
    ProvisionResponse,
    RegenerateResponse,
    TrafficPerServer,
    TrafficResponse,
)
from server_manager.xui.client import XuiClient, XuiError, server_from_doc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clients", dependencies=[Depends(require_api_key)])


def _user_email(user_uid: str) -> str:
    return f"mvm-{user_uid}"


def _subscription_url(sub_id: str) -> str:
    base = settings.public_url.rstrip("/")
    sub_path = settings.sub_path.rstrip("/")
    return f"{base}{sub_path}/{sub_id}"


def _server_sub_url(server_data: Dict[str, Any], sub_id: str) -> Optional[str]:
    public_host = server_data.get("serverPublicHost") or server_data.get("host")
    sub_port = server_data.get("subPort")
    if not public_host or not sub_port:
        return None
    return f"https://{public_host}:{sub_port}/sub/{sub_id}"


def _primary_sub_url(per_server: Dict[str, Dict[str, Any]]) -> Optional[str]:
    for info in per_server.values():
        url = info.get("subUrl")
        if url:
            return str(url)
    return None


def _isoformat(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            return None
    return None


def _healthy_servers_from_db(db: firestore.Client) -> List[firestore.DocumentSnapshot]:
    servers = list(
        db.collection(VPN_SERVERS_COLLECTION)
        .where("status", "==", "healthy")
        .stream()
    )
    random.shuffle(servers)
    return servers


def _new_sub_id() -> str:
    return uuid.uuid4().hex


def _new_client_uuid() -> str:
    return str(uuid.uuid4())


async def _provision_on_server(
    server_doc: firestore.DocumentSnapshot,
    *,
    email: str,
    sub_id: str,
    client_uuid: str,
) -> Tuple[bool, Optional[str]]:
    """Returns (ok, error_message)."""
    data = server_doc.to_dict() or {}
    inbound_id_raw = data.get("defaultInboundId")
    if not inbound_id_raw:
        return False, "no defaultInboundId"
    server = server_from_doc(server_doc.id, data)
    if server is None:
        return False, "missing panel credentials"
    server.default_inbound_id = int(inbound_id_raw)
    try:
        async with XuiClient(server) as xui:
            try:
                await xui.add_client(
                    inbound_id=server.default_inbound_id,
                    client_uuid=client_uuid,
                    email=email,
                    sub_id=sub_id,
                )
            except XuiError as add_exc:
                if "duplicate email" in str(add_exc).lower():
                    inbound = await xui.get_inbound(server.default_inbound_id)
                    settings_raw = inbound.get("settings")
                    settings_obj: Dict[str, Any] = {}
                    if isinstance(settings_raw, str) and settings_raw.strip():
                        settings_obj = json.loads(settings_raw)
                    elif isinstance(settings_raw, dict):
                        settings_obj = settings_raw

                    old_client_uuid: Optional[str] = None
                    for client in settings_obj.get("clients") or []:
                        if str(client.get("email") or "") == email:
                            candidate = str(client.get("id") or "")
                            if candidate:
                                old_client_uuid = candidate
                                break

                    if old_client_uuid:
                        logger.info(
                            "duplicate email found on server_id=%s email=%s; deleting old client id=%s",
                            server_doc.id,
                            email,
                            old_client_uuid,
                        )
                        await xui.del_client(
                            inbound_id=server.default_inbound_id,
                            client_uuid=old_client_uuid,
                        )
                    else:
                        logger.warning(
                            "duplicate email reported but no existing client found server_id=%s email=%s",
                            server_doc.id,
                            email,
                        )

                    await xui.add_client(
                        inbound_id=server.default_inbound_id,
                        client_uuid=client_uuid,
                        email=email,
                        sub_id=sub_id,
                    )
                else:
                    raise
        return True, None
    except (XuiError, Exception) as exc:  # noqa: BLE001
        logger.warning(
            "addClient failed server_id=%s email=%s: %s",
            server_doc.id,
            email,
            exc,
        )
        return False, str(exc)


async def _delete_on_server(
    db: firestore.Client,
    server_id: str,
    client_uuid: str,
) -> None:
    server_snap = await asyncio.to_thread(
        db.collection(VPN_SERVERS_COLLECTION).document(server_id).get
    )
    if not server_snap.exists:
        return
    data = server_snap.to_dict() or {}
    server = server_from_doc(server_snap.id, data)
    if server is None or not data.get("defaultInboundId"):
        return
    inbound_id = int(data["defaultInboundId"])
    try:
        async with XuiClient(server) as xui:
            await xui.del_client(inbound_id=inbound_id, client_uuid=client_uuid)
    except (XuiError, Exception):  # noqa: BLE001
        logger.warning(
            "delClient failed server_id=%s client=%s",
            server_id,
            client_uuid,
            exc_info=True,
        )


def _client_doc_ref(db: firestore.Client, user_uid: str) -> firestore.DocumentReference:
    return db.collection(VPN_CLIENTS_COLLECTION).document(user_uid)


def _initialize_client_record(
    transaction: firestore.Transaction,
    ref: firestore.DocumentReference,
    *,
    user_uid: str,
) -> Dict[str, Any]:
    snap = ref.get(transaction=transaction)
    if snap.exists:
        return snap.to_dict() or {}

    sub_id = _new_sub_id()
    payload = {
        "userUid": user_uid,
        "subId": sub_id,
        "email": _user_email(user_uid),
        "subscriptionUrl": _subscription_url(sub_id),
        "perServer": {},
        "lastTraffic": {"up": 0, "down": 0, "total": 0},
        "provisionedAt": firestore.SERVER_TIMESTAMP,
        "regeneratedAt": None,
        "regenerationCount": 0,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    transaction.set(ref, payload)
    out = dict(payload)
    out["subId"] = sub_id
    out["subscriptionUrl"] = _subscription_url(sub_id)
    return out


@router.post("/provision", response_model=ProvisionResponse)
async def provision_client(payload: ProvisionRequest) -> ProvisionResponse:
    user_uid = payload.userUid.strip()
    if not user_uid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="userUid required")

    db = init_firestore()
    ref = _client_doc_ref(db, user_uid)

    def _ensure_record() -> Dict[str, Any]:
        transaction = db.transaction()

        @firestore.transactional
        def _run(transaction: firestore.Transaction) -> Dict[str, Any]:
            return _initialize_client_record(
                transaction, ref, user_uid=user_uid
            )

        return _run(transaction)

    record = await asyncio.to_thread(_ensure_record)
    sub_id = str(record["subId"])
    email = str(record.get("email") or _user_email(user_uid))
    per_server: Dict[str, Dict[str, Any]] = dict(record.get("perServer") or {})

    healthy = await asyncio.to_thread(_healthy_servers_from_db, db)
    missing = [s for s in healthy if s.id not in per_server]
    if missing:
        per_server, written = await _provision_missing(
            healthy_missing=missing,
            email=email,
            sub_id=sub_id,
            existing=per_server,
        )
        if written:
            await asyncio.to_thread(
                ref.update,
                {
                    "perServer": per_server,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                },
            )

    subscription_url = (
        _primary_sub_url(per_server) or _subscription_url(sub_id)
    )
    stored_sub_url = str(record.get("subscriptionUrl") or "")
    if subscription_url != stored_sub_url:
        await asyncio.to_thread(
            ref.update,
            {
                "subscriptionUrl": subscription_url,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
        )

    return ProvisionResponse(
        subId=sub_id,
        subscriptionUrl=subscription_url,
        perServer=per_server,
    )


async def _provision_missing(
    *,
    healthy_missing: List[firestore.DocumentSnapshot],
    email: str,
    sub_id: str,
    existing: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], bool]:
    """Provisions each server in `healthy_missing` and returns updated map."""
    per_server = dict(existing)
    written = False

    async def _do(server_doc: firestore.DocumentSnapshot) -> Tuple[str, Optional[Dict[str, Any]]]:
        client_uuid = _new_client_uuid()
        ok, _err = await _provision_on_server(
            server_doc,
            email=email,
            sub_id=sub_id,
            client_uuid=client_uuid,
        )
        if not ok:
            return server_doc.id, None
        entry: Dict[str, Any] = {
            "clientUuid": client_uuid,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        sub_url = _server_sub_url(server_doc.to_dict() or {}, sub_id)
        if sub_url:
            entry["subUrl"] = sub_url
        return server_doc.id, entry

    if not healthy_missing:
        return per_server, written

    results = await asyncio.gather(*[_do(s) for s in healthy_missing])
    for server_id, info in results:
        if info is not None:
            per_server[server_id] = info
            written = True
    return per_server, written


@router.post("/regenerate", response_model=RegenerateResponse)
async def regenerate_client(payload: ProvisionRequest) -> RegenerateResponse:
    user_uid = payload.userUid.strip()
    if not user_uid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="userUid required")

    db = init_firestore()
    ref = _client_doc_ref(db, user_uid)

    snap = await asyncio.to_thread(ref.get)
    if not snap.exists:
        # First call ever: behave like provision.
        provisioned = await provision_client(payload)
        return RegenerateResponse(
            subId=provisioned.subId,
            subscriptionUrl=provisioned.subscriptionUrl,
            perServer=provisioned.perServer,
            regeneratedAt=None,
            regenerationCount=0,
        )

    data = snap.to_dict() or {}

    old_per_server: Dict[str, Dict[str, Any]] = dict(data.get("perServer") or {})

    # Best-effort delete from each known server.
    if old_per_server:
        await asyncio.gather(
            *[
                _delete_on_server(db, server_id, str(info.get("clientUuid") or ""))
                for server_id, info in old_per_server.items()
                if info.get("clientUuid")
            ],
            return_exceptions=True,
        )

    new_sub_id = _new_sub_id()
    email = str(data.get("email") or _user_email(user_uid))

    healthy = await asyncio.to_thread(_healthy_servers_from_db, db)

    # Exclude the server(s) the user was previously on so they get a fresh endpoint.
    old_server_ids = set(old_per_server.keys())
    candidates = [s for s in healthy if s.id not in old_server_ids]
    if not candidates:
        # All healthy servers were old ones — fall back to the full pool.
        candidates = list(healthy)

    new_per_server, _written = await _provision_missing(
        healthy_missing=candidates,
        email=email,
        sub_id=new_sub_id,
        existing={},
    )

    new_count = int(data.get("regenerationCount") or 0) + 1
    new_sub_url = _primary_sub_url(new_per_server) or _subscription_url(new_sub_id)
    update_payload = {
        "subId": new_sub_id,
        "subscriptionUrl": new_sub_url,
        "perServer": new_per_server,
        "lastTraffic": {"up": 0, "down": 0, "total": 0},
        "regeneratedAt": firestore.SERVER_TIMESTAMP,
        "regenerationCount": new_count,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    await asyncio.to_thread(ref.set, update_payload, merge=True)

    refreshed = await asyncio.to_thread(ref.get)
    refreshed_data = refreshed.to_dict() or {}
    return RegenerateResponse(
        subId=new_sub_id,
        subscriptionUrl=new_sub_url,
        perServer=new_per_server,
        regeneratedAt=_isoformat(refreshed_data.get("regeneratedAt")),
        regenerationCount=new_count,
    )


@router.get("/{user_uid}/traffic", response_model=TrafficResponse)
async def get_client_traffic(user_uid: str) -> TrafficResponse:
    db = init_firestore()
    snap = await asyncio.to_thread(
        db.collection(VPN_CLIENTS_COLLECTION).document(user_uid).get
    )
    if not snap.exists:
        return TrafficResponse(userUid=user_uid)
    data = snap.to_dict() or {}
    last = dict(data.get("lastTraffic") or {})
    per = {}
    for server_id, info in (data.get("perServerTraffic") or {}).items():
        per[server_id] = TrafficPerServer(
            up=int(info.get("up") or 0),
            down=int(info.get("down") or 0),
            total=int(info.get("total") or 0),
        )
    return TrafficResponse(
        userUid=user_uid,
        up=int(last.get("up") or 0),
        down=int(last.get("down") or 0),
        total=int(last.get("total") or 0),
        syncedAt=_isoformat(last.get("syncedAt")),
        perServer=per,
    )
