"""Periodic 3x-ui panel health probe.

Flips `vpn_servers/{id}.status` between `healthy` and `error` based on whether
the panel responds to a `GET /login`. `provisioning` and `disabled` statuses
are left alone — the install worker and admin actions own those.
"""

import asyncio
import logging
from typing import List

from firebase_admin import firestore

from server_manager.config import settings
from server_manager.firestore_client import VPN_SERVERS_COLLECTION, init_firestore
from server_manager.xui.client import XuiClient, server_from_doc

logger = logging.getLogger(__name__)

_MANAGED_STATUSES = {"healthy", "error"}


async def _probe_one(snap: firestore.DocumentSnapshot) -> None:
    data = snap.to_dict() or {}
    current = str(data.get("status") or "")
    if current not in _MANAGED_STATUSES:
        return
    server = server_from_doc(snap.id, data)
    if server is None:
        return
    healthy = False
    try:
        async with XuiClient(server) as xui:
            healthy = await xui.panel_alive()
    except Exception:  # noqa: BLE001
        logger.debug("panel probe raised", exc_info=True)
    new_status = "healthy" if healthy else "error"
    if new_status == current:
        return
    await asyncio.to_thread(
        snap.reference.update,
        {
            "status": new_status,
            "lastHealthAt": firestore.SERVER_TIMESTAMP,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
    )
    logger.info("server %s status %s -> %s", snap.id, current, new_status)


async def run_health_loop() -> None:
    db = init_firestore()
    interval = max(30, settings.health_interval_s)
    logger.info("health worker started interval=%ss", interval)
    while True:
        try:
            snaps: List[firestore.DocumentSnapshot] = await asyncio.to_thread(
                lambda: list(db.collection(VPN_SERVERS_COLLECTION).stream())
            )
            await asyncio.gather(
                *[_probe_one(snap) for snap in snaps],
                return_exceptions=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("health iteration failed")
        await asyncio.sleep(interval)
