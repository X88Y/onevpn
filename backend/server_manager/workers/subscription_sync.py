"""Periodic sync of subscription expiry status to 3x-ui panels."""

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


def _expiry_ms_from_user_data(user_data: Dict[str, Any]) -> Tuple[int, bool]:
    """Returns (expiry_time_ms, should_enable)."""
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


async def _sync_server(
    server_doc: firestore.DocumentSnapshot,
    clients: List[Dict[str, Any]],
) -> None:
    data = server_doc.to_dict() or {}
    server = server_from_doc(server_doc.id, data)
    if server is None or not data.get("defaultInboundId"):
        return
    inbound_id = int(data["defaultInboundId"])
    try:
        async with XuiClient(server) as xui:
            await xui.login()
            for client in clients:
                try:
                    await xui.update_client(
                        inbound_id=inbound_id,
                        client_uuid=client["uuid"],
                        email=client["email"],
                        sub_id=client["sub_id"],
                        expiry_time=client["expiry_ms"],
                        enable=client["enable"],
                    )
                except (XuiError, Exception):
                    logger.warning(
                        "subscription sync failed server_id=%s user=%s enable=%s",
                        server_doc.id,
                        client["uid"],
                        client["enable"],
                        exc_info=True,
                    )
    except Exception:
        logger.exception("subscription sync failed for server %s", server_doc.id)


async def _sync_once(db: firestore.Client) -> None:
    client_snaps = await asyncio.to_thread(
        lambda: list(db.collection(VPN_CLIENTS_COLLECTION).stream())
    )
    server_snaps = await asyncio.to_thread(
        lambda: list(
            db.collection(VPN_SERVERS_COLLECTION)
            .where("status", "==", "healthy")
            .stream()
        )
    )
    if not client_snaps or not server_snaps:
        return

    # Pre-fetch all user subscription states
    user_snaps = await asyncio.to_thread(
        lambda: list(db.collection("users").stream())
    )
    user_map: Dict[str, Tuple[int, bool]] = {
        snap.id: _expiry_ms_from_user_data(snap.to_dict() or {})
        for snap in user_snaps
    }

    # Group clients by server
    server_clients: Dict[str, List[Dict[str, Any]]] = {}
    for snap in client_snaps:
        data = snap.to_dict() or {}
        per_server = dict(data.get("perServer") or {})
        if not per_server:
            continue
        expiry_ms, is_active = user_map.get(snap.id, (0, False))
        email = str(data.get("email") or f"mvm-{snap.id}")
        sub_id = str(data.get("subId") or "")
        for server_id, info in per_server.items():
            client_uuid = str(info.get("clientUuid") or "")
            if not client_uuid:
                continue
            server_clients.setdefault(server_id, []).append(
                {
                    "uid": snap.id,
                    "uuid": client_uuid,
                    "email": email,
                    "sub_id": sub_id,
                    "expiry_ms": expiry_ms,
                    "enable": is_active,
                }
            )

    tasks = [
        _sync_server(server_doc, server_clients.get(server_doc.id, []))
        for server_doc in server_snaps
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_subscription_sync_loop() -> None:
    db = init_firestore()
    interval = max(60, settings.subscription_sync_interval_s)
    logger.info("subscription sync worker started interval=%ss", interval)
    while True:
        try:
            await _sync_once(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("subscription sync iteration failed")
        await asyncio.sleep(interval)
