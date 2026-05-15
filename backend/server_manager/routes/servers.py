import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from firebase_admin import firestore

from server_manager.auth import require_api_key
from server_manager.crypto import encrypt_str
from server_manager.firestore_client import (
    VPN_INSTALL_JOBS_COLLECTION,
    VPN_SERVERS_COLLECTION,
    init_firestore,
)
from server_manager.models import (
    CreateServerRequest,
    CreateServerResponse,
    InstallJobResponse,
    ServerSummary,
    ServerListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", dependencies=[Depends(require_api_key)])


def _isoformat(value) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            return None
    return None


@router.post("/servers", response_model=CreateServerResponse)
async def create_server(payload: CreateServerRequest) -> CreateServerResponse:
    db = init_firestore()
    server_doc = db.collection(VPN_SERVERS_COLLECTION).document()
    job_doc = db.collection(VPN_INSTALL_JOBS_COLLECTION).document()

    now = datetime.now(timezone.utc)
    batch = db.batch()
    batch.set(
        server_doc,
        {
            "host": payload.host.strip(),
            "sshPort": payload.sshPort or 22,
            "sshUser": payload.login.strip(),
            "sshPasswordCt": encrypt_str(payload.password),
            "label": (payload.label or "").strip() or None,
            "countryCode": (payload.countryCode or "").strip().upper() or None,
            "status": "provisioning",
            "addedAt": firestore.SERVER_TIMESTAMP,
            "updatedAt": firestore.SERVER_TIMESTAMP,
            "clientCount": 0,
            "lastHealthAt": None,
            "panelUrl": None,
            "panelUser": None,
            "panelPasswordCt": None,
            "panelWebBasePath": None,
            "defaultInboundId": None,
            "serverPublicHost": payload.host.strip(),
            "subPort": None,
        },
    )
    batch.set(
        job_doc,
        {
            "serverId": server_doc.id,
            "status": "pending",
            "progress": "queued",
            "log": "",
            "error": None,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
    )
    batch.commit()

    logger.info(
        "queued server install host=%s server_id=%s job_id=%s",
        payload.host,
        server_doc.id,
        job_doc.id,
    )
    return CreateServerResponse(serverId=server_doc.id, jobId=job_doc.id)


@router.get("/install_jobs/{job_id}", response_model=InstallJobResponse)
async def get_install_job(job_id: str) -> InstallJobResponse:
    db = init_firestore()
    snap = db.collection(VPN_INSTALL_JOBS_COLLECTION).document(job_id).get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")
    data = snap.to_dict() or {}
    server_id = str(data.get("serverId") or "")

    panel_url: Optional[str] = None
    panel_user: Optional[str] = None
    panel_password: Optional[str] = None
    if data.get("status") == "done" and server_id:
        server_snap = (
            db.collection(VPN_SERVERS_COLLECTION).document(server_id).get()
        )
        if server_snap.exists:
            sdata = server_snap.to_dict() or {}
            panel_url = sdata.get("panelUrl")
            panel_user = sdata.get("panelUser")
            # Plaintext panel password is intentionally NOT returned. The job
            # response includes the one-time `panelPasswordOnce` field at
            # install time only (see install_worker).
            panel_password = data.get("panelPasswordOnce")

    return InstallJobResponse(
        jobId=job_id,
        serverId=server_id,
        status=str(data.get("status") or "unknown"),
        progress=data.get("progress"),
        error=data.get("error"),
        panelUrl=panel_url,
        panelUser=panel_user,
        panelPassword=panel_password,
        log=data.get("log"),
    )


@router.get("/servers", response_model=ServerListResponse)
async def list_servers(page: int = 1, limit: int = 10) -> ServerListResponse:
    db = init_firestore()
    snaps = db.collection(VPN_SERVERS_COLLECTION).stream()
    all_servers: List[ServerSummary] = []
    for snap in snaps:
        data = snap.to_dict() or {}
        if data.get("deleted"):
            continue
        all_servers.append(
            ServerSummary(
                id=snap.id,
                host=str(data.get("host") or ""),
                label=data.get("label"),
                countryCode=data.get("countryCode"),
                status=str(data.get("status") or "unknown"),
                panelUrl=data.get("panelUrl"),
                clientCount=int(data.get("clientCount") or 0),
                addedAt=_isoformat(data.get("addedAt")),
                lastHealthAt=_isoformat(data.get("lastHealthAt")),
            )
        )
    
    # Sort by addedAt desc (newest first)
    all_servers.sort(key=lambda x: x.addedAt or "", reverse=True)
    
    total = len(all_servers)
    start = (page - 1) * limit
    end = start + limit
    paged_servers = all_servers[start:end]
    
    return ServerListResponse(total=total, servers=paged_servers)


async def _get_server_ref(db: firestore.Client, sid: str) -> firestore.DocumentReference:
    """Resolves a server reference by its Firestore ID or its public host (IP)."""

    def _sync_find():
        # 1. Try as Firestore document ID
        ref = db.collection(VPN_SERVERS_COLLECTION).document(sid)
        snap = ref.get()
        if snap.exists and not snap.to_dict().get("deleted"):
            return ref
        # 2. Try as host (IP)
        snaps = list(
            db.collection(VPN_SERVERS_COLLECTION).where("host", "==", sid.strip()).limit(5).stream()
        )
        for s in snaps:
            if not s.to_dict().get("deleted"):
                return s.reference
        return None

    ref = await asyncio.to_thread(_sync_find)
    if not ref:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="server not found")
    return ref


@router.post("/servers/{server_id}/disable")
async def disable_server(server_id: str) -> dict:
    db = init_firestore()
    ref = await _get_server_ref(db, server_id)
    ref.update({"status": "disabled", "updatedAt": firestore.SERVER_TIMESTAMP})
    return {"ok": True}


@router.post("/servers/{server_id}/enable")
async def enable_server(server_id: str) -> dict:
    db = init_firestore()
    ref = await _get_server_ref(db, server_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="server not found")
    data = snap.to_dict() or {}
    if not data.get("panelUrl"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="server has no panel; install first"
        )
    ref.update({"status": "healthy", "updatedAt": firestore.SERVER_TIMESTAMP})
    return {"ok": True}


@router.post("/servers/{server_id}/error")
async def set_server_error(server_id: str) -> dict:
    db = init_firestore()
    ref = await _get_server_ref(db, server_id)
    ref.update({"status": "error", "updatedAt": firestore.SERVER_TIMESTAMP})
    return {"ok": True}


@router.delete("/servers/{server_id}")
async def delete_server(server_id: str) -> dict:
    db = init_firestore()
    ref = await _get_server_ref(db, server_id)
    ref.update({
        "status": "disabled",
        "deleted": True,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    })
    return {"ok": True}
