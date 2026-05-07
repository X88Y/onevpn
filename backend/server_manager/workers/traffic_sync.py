"""Periodic per-user traffic synchronization across the server pool."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from firebase_admin import firestore

from server_manager.config import settings
from server_manager.firestore_client import (
    VPN_CLIENTS_COLLECTION,
    VPN_SERVERS_COLLECTION,
    init_firestore,
)
from server_manager.xui.client import XuiClient, XuiError, server_from_doc

logger = logging.getLogger(__name__)


async def _fetch_server_traffics(
    server_doc: firestore.DocumentSnapshot,
    emails: List[str],
) -> Dict[str, Tuple[int, int]]:
    """Returns {email: (up, down)} from the server's panel."""
    server = server_from_doc(server_doc.id, server_doc.to_dict() or {})
    if server is None:
        return {}
    out: Dict[str, Tuple[int, int]] = {}
    try:
        async with XuiClient(server) as xui:
            await xui.login()
            for email in emails:
                try:
                    data = await xui.get_client_traffics(email)
                except (XuiError, Exception):  # noqa: BLE001
                    continue
                if not data:
                    continue
                up = int(data.get("up") or 0)
                down = int(data.get("down") or 0)
                out[email] = (up, down)
    except Exception:  # noqa: BLE001
        logger.exception("traffic fetch failed for server %s", server_doc.id)
    return out


async def _sync_once(db: firestore.Client) -> None:
    server_snaps = await asyncio.to_thread(
        lambda: list(
            db.collection(VPN_SERVERS_COLLECTION)
            .where("status", "==", "healthy")
            .stream()
        )
    )
    client_snaps = await asyncio.to_thread(
        lambda: list(db.collection(VPN_CLIENTS_COLLECTION).stream())
    )
    if not server_snaps or not client_snaps:
        return

    email_to_uid: Dict[str, str] = {}
    for snap in client_snaps:
        data = snap.to_dict() or {}
        email = str(data.get("email") or "").strip()
        if email:
            email_to_uid[email] = snap.id

    emails = list(email_to_uid.keys())
    server_results = await asyncio.gather(
        *[_fetch_server_traffics(snap, emails) for snap in server_snaps]
    )

    # uid -> server_id -> (up, down)
    aggregate: Dict[str, Dict[str, Tuple[int, int]]] = {}
    for snap, per_email in zip(server_snaps, server_results):
        for email, (up, down) in per_email.items():
            uid = email_to_uid.get(email)
            if not uid:
                continue
            aggregate.setdefault(uid, {})[snap.id] = (up, down)

    now_iso = datetime.now(timezone.utc).isoformat()
    for uid, per_server in aggregate.items():
        total_up = sum(up for up, _ in per_server.values())
        total_down = sum(down for _, down in per_server.values())
        per_server_payload: Dict[str, Dict[str, int]] = {
            server_id: {
                "up": int(up),
                "down": int(down),
                "total": int(up + down),
            }
            for server_id, (up, down) in per_server.items()
        }
        ref = db.collection(VPN_CLIENTS_COLLECTION).document(uid)
        await asyncio.to_thread(
            ref.set,
            {
                "lastTraffic": {
                    "up": int(total_up),
                    "down": int(total_down),
                    "total": int(total_up + total_down),
                    "syncedAt": now_iso,
                },
                "perServerTraffic": per_server_payload,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )


async def run_traffic_sync_loop() -> None:
    db = init_firestore()
    interval = max(30, settings.traffic_sync_interval_s)
    logger.info("traffic sync worker started interval=%ss", interval)
    while True:
        try:
            await _sync_once(db)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("traffic sync iteration failed")
        await asyncio.sleep(interval)
