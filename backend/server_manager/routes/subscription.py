"""Public subscription aggregator.

`GET /sub/{subId}` returns a single body that VPN client apps understand:
either a base64-encoded list of `vless://...` lines or the raw concatenated
list. We fetch each healthy server's per-panel subscription URL
(`https://serverPublicHost:subPort/sub/{subId}`) in parallel, decode each
response if it looks base64-encoded, then re-encode the merged list.

This endpoint is intentionally unauthenticated; subId is a 128-bit secret
that acts as a bearer token (matches how Xray subscription URLs work).
"""

import asyncio
import base64
import logging
from typing import List

import httpx
from fastapi import APIRouter, HTTPException, Response, status

from server_manager.config import settings
from server_manager.firestore_client import (
    VPN_CLIENTS_COLLECTION,
    VPN_SERVERS_COLLECTION,
    init_firestore,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _try_b64_decode(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    if stripped.lower().startswith(("vless://", "vmess://", "ss://", "trojan://")):
        return stripped
    try:
        padded = stripped + "=" * (-len(stripped) % 4)
        decoded = base64.b64decode(padded, validate=False).decode("utf-8")
        if any(
            decoded.lower().startswith(prefix)
            for prefix in ("vless://", "vmess://", "ss://", "trojan://")
        ):
            return decoded
    except Exception:  # noqa: BLE001
        pass
    return stripped


async def _fetch_server_lines(
    http: httpx.AsyncClient,
    server_data: dict,
    sub_id: str,
) -> List[str]:
    public_host = server_data.get("serverPublicHost") or server_data.get("host")
    sub_port = server_data.get("subPort")
    if not public_host or not sub_port:
        return []
    url = f"https://{public_host}:{sub_port}/sub/{sub_id}"
    try:
        response = await http.get(url, timeout=15.0)
    except httpx.HTTPError as exc:
        logger.info("subscription fetch failed url=%s: %s", url, exc)
        return []
    if response.status_code != 200:
        return []
    decoded = _try_b64_decode(response.text)
    return [line.strip() for line in decoded.splitlines() if line.strip()]


@router.get("/sub/{sub_id}")
async def aggregate_subscription(sub_id: str) -> Response:
    db = init_firestore()
    sub_id = sub_id.strip()
    if not sub_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="subId required")

    client_query = (
        db.collection(VPN_CLIENTS_COLLECTION)
        .where("subId", "==", sub_id)
        .limit(1)
        .stream()
    )
    client_snap = next(iter(client_query), None)
    if client_snap is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown subId")

    server_snaps = list(
        db.collection(VPN_SERVERS_COLLECTION).where("status", "==", "healthy").stream()
    )

    async with httpx.AsyncClient(verify=False, follow_redirects=True) as http:
        results = await asyncio.gather(
            *[
                _fetch_server_lines(http, snap.to_dict() or {}, sub_id)
                for snap in server_snaps
            ]
        )

    seen = set()
    merged: List[str] = []
    for lines in results:
        for line in lines:
            if line in seen:
                continue
            seen.add(line)
            merged.append(line)

    body = "\n".join(merged) + ("\n" if merged else "")
    payload = base64.b64encode(body.encode("utf-8")).decode("ascii")
    return Response(
        content=payload,
        media_type="text/plain; charset=utf-8",
        headers={
            "Profile-Update-Interval": "12",
            "Content-Disposition": f"inline; filename=\"mvm-{sub_id[:8]}\"",
        },
    )
