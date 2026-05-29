from pydantic import BaseModel
import random
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
from server_manager.remnawave.client import RemnawaveError, update_user as remnawave_update_user
from server_manager.xui.client import XuiClient, XuiError, server_from_doc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clients", dependencies=[Depends(require_api_key)])


def _user_email(user_uid: str) -> str:
    return f"mvm-{user_uid}"


def _subscription_state_from_user(user_data: Dict[str, Any]) -> Tuple[int, bool]:
    """Returns (expiry_time_ms, enable) from a user document dict."""
    end = user_data.get("subscriptionEndsAt")
    if end is None:
        return 0, False
    if hasattr(end, "timestamp"):
        end_ts = end.timestamp()
    else:
        try:
            end_ts = datetime.fromisoformat(str(end)).timestamp()
        except Exception:  # noqa: BLE001
            return 0, False
    now_ts = datetime.now(timezone.utc).timestamp()
    expiry_ms = int(end_ts * 1000)
    return expiry_ms, end_ts > now_ts


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


def _extract_host_from_url(url: Optional[str]) -> Optional[str]:
    """Extracts the hostname/IP from a subscription URL like https://1.2.3.4:2096/sub/..."""
    if not url:
        return None
    try:
        without_scheme = url.split("://", 1)[-1]
        host_port = without_scheme.split("/")[0]
        host = host_port.rsplit(":", 1)[0]
        return host if host else None
    except Exception:  # noqa: BLE001
        return None


def _server_host(server_data: Dict[str, Any]) -> Optional[str]:
    """Returns the public host of a server document."""
    return server_data.get("serverPublicHost") or server_data.get("host") or None


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
    expiry_time: int = 0,
    enable: bool = True,
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
                    expiry_time=expiry_time,
                    enable=enable,
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
                        expiry_time=expiry_time,
                        enable=enable,
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

    # Fetch user subscription state for panel-side expiry / enablement
    user_snap = await asyncio.to_thread(
        db.collection("users").document(user_uid).get
    )
    expiry_ms = 0
    enable = True
    if user_snap.exists:
        expiry_ms, enable = _subscription_state_from_user(user_snap.to_dict() or {})

    healthy = await asyncio.to_thread(_healthy_servers_from_db, db)
    missing = [s for s in healthy if s.id not in per_server]
    if missing:
        per_server, written = await _provision_missing(
            healthy_missing=missing,
            email=email,
            sub_id=sub_id,
            existing=per_server,
            expiry_time=expiry_ms,
            enable=enable,
        )
        if written:
            await asyncio.to_thread(
                ref.update,
                {
                    "perServer": per_server,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                },
            )

    subscription_url = _subscription_url(sub_id)
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
    expiry_time: int = 0,
    enable: bool = True,
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
            expiry_time=expiry_time,
            enable=enable,
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

    # Determine the current server's host so we never give the user the same IP again.
    current_sub_url = str(data.get("subscriptionUrl") or "")
    current_host = _extract_host_from_url(current_sub_url)

    # Also collect hosts from all per-server sub-URLs as a fallback.
    current_hosts: set = set()
    if current_host:
        current_hosts.add(current_host)
    for info in old_per_server.values():
        h = _extract_host_from_url(info.get("subUrl"))
        if h:
            current_hosts.add(h)

    # Exclude any server whose public host matches one the user currently has.
    candidates = [
        s for s in healthy
        if _server_host(s.to_dict() or {}) not in current_hosts
    ]

    if not candidates:
        # No alternative healthy servers available — signal the client to retry later.
        current_hosts = [current_host]
        candidates = [
            s for s in healthy
            if _server_host(s.to_dict() or {}) not in current_hosts
        ]
        if not candidates:
            candidates = healthy

    random.shuffle(candidates)

    # Fetch user subscription state for panel-side expiry / enablement
    user_snap = await asyncio.to_thread(
        db.collection("users").document(user_uid).get
    )
    expiry_ms = 0
    enable = True
    if user_snap.exists:
        expiry_ms, enable = _subscription_state_from_user(user_snap.to_dict() or {})

    new_per_server, _written = await _provision_missing(
        healthy_missing=candidates,
        email=email,
        sub_id=new_sub_id,
        existing={},
        expiry_time=expiry_ms,
        enable=enable,
    )

    new_count = int(data.get("regenerationCount") or 0) + 1
    new_sub_url = _subscription_url(new_sub_id)
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


class SyncRemnawaveResponse(BaseModel):
    ok: bool
    userUid: str
    status: Optional[str] = None
    skipped: bool = False


@router.post("/sync-remnawave", response_model=SyncRemnawaveResponse)
async def sync_remnawave_user(payload: ProvisionRequest) -> SyncRemnawaveResponse:
    """Immediately pushes a single user's subscription state to Remnawave.

    Called by Firebase Cloud Functions right after a successful payment so
    the VPN access is updated without waiting for the periodic sync worker.
    Silently skips (returns ``skipped=True``) when Remnawave is not configured
    or the user has no ``remnawaveUuid`` stored in Firestore.
    """
    from server_manager.config import settings as _settings

    user_uid = payload.userUid.strip()
    if not user_uid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="userUid required")

    if not _settings.remnawave_base_url or not _settings.remnawave_api_token:
        return SyncRemnawaveResponse(ok=True, userUid=user_uid, skipped=True)

    db = init_firestore()
    user_snap = await asyncio.to_thread(db.collection("users").document(user_uid).get)
    if not user_snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    data = user_snap.to_dict() or {}
    rw_uuid = data.get("remnawaveUuid")
    if not rw_uuid:
        return SyncRemnawaveResponse(ok=True, userUid=user_uid, skipped=True)

    from datetime import datetime, timezone

    end = data.get("subscriptionEndsAt")
    expire_at: Optional[datetime] = None
    is_active = False
    if end is not None:
        end_dt: Optional[datetime] = None
        if hasattr(end, "timestamp"):
            end_dt = end
            if not hasattr(end_dt, "tzinfo") or end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
        else:
            try:
                end_dt = datetime.fromisoformat(str(end))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
            except Exception:  # noqa: BLE001
                end_dt = None
        if end_dt is not None:
            expire_at = end_dt
            is_active = end_dt > datetime.now(timezone.utc)

    if expire_at is None:
        expire_at = datetime.now(timezone.utc)

    rw_status = "ACTIVE" if is_active else "DISABLED"

    tier = data.get("subscriptionTier")
    squad_kwargs = {}
    if is_active:
        # Constants from constants/env
        PREMIUM_EXTERNAL_SQUAD_UUID = "d997add1-ecf9-43aa-874c-f235426ffef0"
        PREMIUM_INTERNAL_SQUAD_UUID = "c2b488c4-2509-476c-923f-6620570ee3cc"

        if tier == "premium":
            squad_kwargs["active_internal_squads"] = [PREMIUM_INTERNAL_SQUAD_UUID]
            squad_kwargs["external_squad_uuid"] = PREMIUM_EXTERNAL_SQUAD_UUID
        else:
            import os
            default_squad = os.getenv("REMNAWAVE_INTERNAL_SQUAD_UUID")
            squad_kwargs["active_internal_squads"] = [default_squad] if default_squad else []
            squad_kwargs["external_squad_uuid"] = None

    try:
        await remnawave_update_user(
            uuid=str(rw_uuid),
            expire_at=expire_at,
            status=rw_status,
            **squad_kwargs,
        )
    except RemnawaveError as exc:
        logger.warning("sync-remnawave skipped (not configured): %s", exc)
        return SyncRemnawaveResponse(ok=True, userUid=user_uid, skipped=True)
    except Exception:
        logger.exception("sync-remnawave failed user_uid=%s rw_uuid=%s", user_uid, rw_uuid)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Failed to sync with Remnawave",
        )

    logger.info(
        "sync-remnawave ok user_uid=%s rw_uuid=%s status=%s expire_at=%s squads=%s",
        user_uid,
        rw_uuid,
        rw_status,
        expire_at.isoformat(),
        squad_kwargs,
    )
    return SyncRemnawaveResponse(ok=True, userUid=user_uid, status=rw_status)
