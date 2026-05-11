"""Periodic Prometheus targets sync.

Reads `vpn_servers` from Firestore and writes healthy ones to a `targets.json`
file for Prometheus file-based service discovery.
"""

import asyncio
import json
import logging
import os
from typing import List

from firebase_admin import firestore

from server_manager.config import settings
from server_manager.firestore_client import VPN_SERVERS_COLLECTION, init_firestore

logger = logging.getLogger(__name__)

# Default path if not specified in env
DEFAULT_TARGETS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "monitoring", "prometheus", "targets.json"
)

async def run_monitoring_sync_loop() -> None:
    db = init_firestore()
    interval = getattr(settings, "monitoring_sync_interval_s", 60)
    targets_path = getattr(settings, "monitoring_targets_path", DEFAULT_TARGETS_PATH)
    
    logger.info("monitoring sync worker started interval=%ss path=%s", interval, targets_path)
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(targets_path), exist_ok=True)

    while True:
        try:
            snaps: List[firestore.DocumentSnapshot] = await asyncio.to_thread(
                lambda: list(db.collection(VPN_SERVERS_COLLECTION).stream())
            )
            
            targets = []
            for snap in snaps:
                data = snap.to_dict() or {}
                if data.get("deleted") or data.get("status") != "healthy":
                    continue
                
                host = data.get("host")
                if not host:
                    continue
                
                # node_exporter runs on port 9100 by default
                targets.append({
                    "targets": [f"{host}:9100"],
                    "labels": {
                        "job": "vpn_nodes",
                        "server_id": snap.id,
                        "label": data.get("label") or snap.id,
                    }
                })
            
            # Write to temporary file first then rename to ensure atomicity
            tmp_path = f"{targets_path}.tmp"
            with open(tmp_path, "w") as f:
                json.dump(targets, f, indent=2)
            os.replace(tmp_path, targets_path)
            
            logger.debug("synced %d targets to %s", len(targets), targets_path)
            
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("monitoring sync iteration failed")
            
        await asyncio.sleep(interval)
