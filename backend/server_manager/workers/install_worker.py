"""Background worker that drains `vpn_install_jobs` and runs SSH installs."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from firebase_admin import firestore

from server_manager.config import settings
from server_manager.crypto import decrypt_str, encrypt_str
from server_manager.firestore_client import (
    VPN_INSTALL_JOBS_COLLECTION,
    VPN_SERVERS_COLLECTION,
    init_firestore,
)
from server_manager.ssh.installer import SshTarget, run_install
from server_manager.xui.client import XuiClient, XuiServer
from server_manager.xui.inbound import (
    build_default_vless_reality_payload,
    random_inbound_port,
)

MOCK_CLIENT_COUNT = 3

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _claim_job(db: firestore.Client) -> Optional[firestore.DocumentSnapshot]:
    def _txn() -> Optional[firestore.DocumentSnapshot]:
        snaps = (
            db.collection(VPN_INSTALL_JOBS_COLLECTION)
            .where("status", "==", "pending")
            .limit(1)
            .get()
        )
        if not snaps:
            return None
        snap = snaps[0]
        ref = snap.reference
        transaction = db.transaction()

        @firestore.transactional
        def _claim(transaction: firestore.Transaction) -> Optional[firestore.DocumentSnapshot]:
            current = ref.get(transaction=transaction)
            data = current.to_dict() or {}
            if data.get("status") != "pending":
                return None
            transaction.update(
                ref,
                {
                    "status": "running",
                    "progress": "claimed",
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                },
            )
            return current

        return _claim(transaction)

    return await asyncio.to_thread(_txn)


def _update_job_progress(
    db: firestore.Client, job_id: str, line: str
) -> None:
    """Best-effort progress writer; intentionally drops failures."""
    try:
        db.collection(VPN_INSTALL_JOBS_COLLECTION).document(job_id).update(
            {
                "progress": line[:512],
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
        )
    except Exception:  # noqa: BLE001
        logger.debug("could not write job progress", exc_info=True)


async def _ensure_default_inbound(
    panel_url: str,
    panel_user: str,
    panel_password: str,
) -> Optional[int]:
    """Returns the inbound id we should use for new clients."""
    server = XuiServer(
        server_id="installer",
        panel_url=panel_url,
        username=panel_user,
        password=panel_password,
    )
    logger.info("_ensure_default_inbound: panel_url=%s user=%s", panel_url, panel_user)
    # After `x-ui restart` the listener may not accept connections immediately.
    backoff_s = (0, 2, 4, 8, 12, 20)
    last_network_error: Optional[BaseException] = None
    for attempt, wait in enumerate(backoff_s):
        if wait:
            logger.info(
                "waiting %ss before attempt %s/%s (panel_url=%s)",
                wait,
                attempt + 1,
                len(backoff_s),
                panel_url,
            )
            await asyncio.sleep(wait)
        logger.info(
            "connecting to panel API attempt %s/%s url=%s",
            attempt + 1,
            len(backoff_s),
            panel_url,
        )
        try:
            async with XuiClient(server) as xui:
                logger.info("attempt %s: logging in to panel", attempt + 1)
                await xui.login()
                logger.info("attempt %s: login OK, listing inbounds", attempt + 1)
                inbounds = await xui.list_inbounds()
                logger.info(
                    "attempt %s: got %s inbound(s): %s",
                    attempt + 1,
                    len(inbounds),
                    [
                        {"id": i.get("id"), "protocol": i.get("protocol"), "remark": i.get("remark")}
                        for i in inbounds
                    ],
                )
                # Reuse an existing VLESS inbound if present.
                for inbound in inbounds:
                    if str(inbound.get("protocol") or "").lower() == "vless":
                        inbound_id = int(inbound.get("id") or 0)
                        if inbound_id:
                            logger.info(
                                "reusing existing VLESS inbound id=%s remark=%s",
                                inbound_id,
                                inbound.get("remark"),
                            )
                            return inbound_id

                logger.info("no existing VLESS inbound; creating mvm-default")
                inbound_port = random_inbound_port()
                logger.info("creating VLESS TCP REALITY inbound on port %s", inbound_port)
                
                cert = await xui.new_x25519_cert()
                private_key = cert["privateKey"] if cert else ""
                public_key = cert["publicKey"] if cert else ""

                payload = build_default_vless_reality_payload(
                    port=inbound_port,
                    private_key=private_key,
                    public_key=public_key,
                    remark="mvm-default",
                )
                try:
                    await xui.add_inbound(payload)
                    logger.info("addInbound succeeded")
                except Exception:  # noqa: BLE001
                    logger.exception("addInbound failed")
                    return None

                inbounds = await xui.list_inbounds()
                logger.info(
                    "post-create inbounds (%s total): %s",
                    len(inbounds),
                    [
                        {"id": i.get("id"), "protocol": i.get("protocol"), "remark": i.get("remark")}
                        for i in inbounds
                    ],
                )
                for inbound in inbounds:
                    if (
                        str(inbound.get("protocol") or "").lower() == "vless"
                        and str(inbound.get("remark") or "") == "mvm-default"
                    ):
                        inbound_id = int(inbound.get("id") or 0)
                        if inbound_id:
                            logger.info("mvm-default inbound created with id=%s", inbound_id)
                            return inbound_id
                logger.error("mvm-default inbound not found after addInbound")
                return None
        except httpx.RequestError as exc:
            last_network_error = exc
            logger.warning(
                "panel API unreachable (attempt %s/%s) url=%s error_type=%s msg=%s",
                attempt + 1,
                len(backoff_s),
                panel_url,
                type(exc).__name__,
                exc,
            )
            continue
        except Exception:  # noqa: BLE001
            logger.exception(
                "unexpected error while ensuring default inbound (attempt %s/%s) url=%s",
                attempt + 1,
                len(backoff_s),
                panel_url,
            )
            return None

    logger.error(
        "could not reach panel API after %s attempts url=%s error_type=%s msg=%s",
        len(backoff_s),
        panel_url,
        type(last_network_error).__name__ if last_network_error else "None",
        last_network_error,
    )
    return None


async def _seed_mock_clients(
    panel_url: str,
    panel_user: str,
    panel_password: str,
    inbound_id: int,
) -> None:
    """Add MOCK_CLIENT_COUNT placeholder clients so the inbound is never empty."""
    server = XuiServer(
        server_id="installer",
        panel_url=panel_url,
        username=panel_user,
        password=panel_password,
    )
    async with XuiClient(server) as xui:
        for i in range(1, MOCK_CLIENT_COUNT + 1):
            client_uuid = str(uuid.uuid4())
            sub_id = uuid.uuid4().hex
            email = f"mvm-mock-{i}"
            try:
                await xui.add_client(
                    inbound_id=inbound_id,
                    client_uuid=client_uuid,
                    email=email,
                    sub_id=sub_id,
                )
                logger.info("seeded mock client %s on inbound %s", email, inbound_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "could not seed mock client %s on inbound %s",
                    email,
                    inbound_id,
                    exc_info=True,
                )


async def _run_install_for_job(
    db: firestore.Client,
    job_snap: firestore.DocumentSnapshot,
) -> None:
    job_id = job_snap.id
    data = job_snap.to_dict() or {}
    server_id = str(data.get("serverId") or "")
    if not server_id:
        await asyncio.to_thread(
            job_snap.reference.update,
            {
                "status": "error",
                "error": "missing serverId",
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
        )
        return

    server_ref = db.collection(VPN_SERVERS_COLLECTION).document(server_id)
    server_snap = await asyncio.to_thread(server_ref.get)
    if not server_snap.exists:
        await asyncio.to_thread(
            job_snap.reference.update,
            {
                "status": "error",
                "error": "server document missing",
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
        )
        return

    server_data = server_snap.to_dict() or {}
    try:
        ssh_password = decrypt_str(str(server_data.get("sshPasswordCt") or ""))
    except RuntimeError as exc:
        await asyncio.to_thread(
            job_snap.reference.update,
            {
                "status": "error",
                "error": f"could not decrypt SSH password: {exc}",
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
        )
        return

    target = SshTarget(
        host=str(server_data.get("host") or ""),
        username=str(server_data.get("sshUser") or ""),
        password=ssh_password,
        port=int(server_data.get("sshPort") or 22),
    )

    loop = asyncio.get_running_loop()

    def _progress(line: str) -> None:
        loop.call_soon_threadsafe(_update_job_progress, db, job_id, line)

    try:
        outcome = await asyncio.wait_for(
            run_install(target, progress_cb=_progress),
            timeout=settings.install_timeout_s,
        )
    except asyncio.TimeoutError:
        await asyncio.to_thread(
            job_snap.reference.update,
            {
                "status": "error",
                "error": f"install timed out after {settings.install_timeout_s}s",
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
        )
        await asyncio.to_thread(
            server_ref.update,
            {
                "status": "error",
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
        )
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("install failed for server %s", server_id)
        await asyncio.to_thread(
            job_snap.reference.update,
            {
                "status": "error",
                "error": str(exc)[:500],
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
        )
        await asyncio.to_thread(
            server_ref.update,
            {
                "status": "error",
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
        )
        return

    inbound_id: Optional[int] = None
    try:
        inbound_id = await _ensure_default_inbound(
            outcome.panel_url, outcome.panel_user, outcome.panel_password
        )
    except Exception:  # noqa: BLE001
        logger.exception("could not ensure default inbound")

    update = {
        "panelUrl": outcome.panel_url,
        "panelUser": outcome.panel_user,
        "panelPasswordCt": encrypt_str(outcome.panel_password),
        "panelWebBasePath": outcome.panel_web_base_path,
        "subPort": outcome.sub_port,
        "serverPublicHost": outcome.server_public_host,
        "defaultInboundId": inbound_id,
        "status": "healthy" if inbound_id else "error",
        "lastHealthAt": firestore.SERVER_TIMESTAMP,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    await asyncio.to_thread(server_ref.set, update, merge=True)

    if inbound_id:
        try:
            await _seed_mock_clients(
                outcome.panel_url,
                outcome.panel_user,
                outcome.panel_password,
                inbound_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning("mock client seeding failed (non-fatal)", exc_info=True)

    await asyncio.to_thread(
        job_snap.reference.update,
        {
            "status": "done" if inbound_id else "error",
            "progress": "completed" if inbound_id else "panel reachable but no inbound",
            "log": outcome.log,
            "panelPasswordOnce": outcome.panel_password,  # readable once via API
            "completedAt": firestore.SERVER_TIMESTAMP,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
    )


async def run_install_loop() -> None:
    db = init_firestore()
    interval = max(1, settings.install_poll_interval_s)
    logger.info("install worker started interval=%ss", interval)
    while True:
        try:
            job = await _claim_job(db)
            if job is None:
                await asyncio.sleep(interval)
                continue
            await _run_install_for_job(db, job)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("install worker iteration failed")
            await asyncio.sleep(interval)
