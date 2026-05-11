"""Async wrapper around the 3x-ui (MHSanaei) panel HTTP API."""

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from server_manager.config import settings
from server_manager.crypto import decrypt_str
from server_manager.xui.inbound import build_client_object

logger = logging.getLogger(__name__)


class XuiError(RuntimeError):
    pass


@dataclass
class XuiServer:
    server_id: str
    panel_url: str  # full base, e.g. https://1.2.3.4:54321/abcdef0123456789
    username: str
    password: str
    default_inbound_id: Optional[int] = None


def server_from_doc(doc_id: str, data: Dict[str, Any]) -> Optional[XuiServer]:
    panel_url = data.get("panelUrl")
    panel_user = data.get("panelUser")
    panel_password_ct = data.get("panelPasswordCt")
    if not panel_url or not panel_user or not panel_password_ct:
        return None
    try:
        panel_password = decrypt_str(panel_password_ct)
    except RuntimeError:
        logger.exception("failed to decrypt panel password for server %s", doc_id)
        return None
    return XuiServer(
        server_id=doc_id,
        panel_url=str(panel_url).rstrip("/"),
        username=str(panel_user),
        password=panel_password,
        default_inbound_id=(
            int(data["defaultInboundId"]) if data.get("defaultInboundId") else None
        ),
    )


class XuiClient:
    """One short-lived client per request; logs in lazily."""

    def __init__(self, server: XuiServer, *, verify: bool = False) -> None:
        self._server = server
        self._client = httpx.AsyncClient(
            base_url=server.panel_url,
            verify=verify,
            timeout=settings.panel_request_timeout,
            follow_redirects=True,
        )
        self._logged_in = False

    @property
    def server(self) -> XuiServer:
        return self._server

    async def __aenter__(self) -> "XuiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._client.aclose()

    async def login(self) -> None:
        if self._logged_in:
            return
        response = await self._client.post(
            "/login",
            data={
                "username": self._server.username,
                "password": self._server.password,
            },
        )
        response.raise_for_status()
        body = self._json(response)
        if not body.get("success"):
            raise XuiError(f"login failed: {body.get('msg')}")
        self._logged_in = True

    async def list_inbounds(self) -> List[Dict[str, Any]]:
        await self.login()
        response = await self._client.get("/panel/api/inbounds/list")
        response.raise_for_status()
        body = self._json(response)
        if not body.get("success"):
            raise XuiError(f"list inbounds failed: {body.get('msg')}")
        return list(body.get("obj") or [])

    async def get_inbound(self, inbound_id: int) -> Dict[str, Any]:
        await self.login()
        response = await self._client.get(f"/panel/api/inbounds/get/{inbound_id}")
        response.raise_for_status()
        body = self._json(response)
        if not body.get("success"):
            raise XuiError(f"get inbound failed: {body.get('msg')}")
        return dict(body.get("obj") or {})

    async def add_inbound(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.login()
        response = await self._client.post("/panel/api/inbounds/add", json=payload)
        response.raise_for_status()
        body = self._json(response)
        if not body.get("success"):
            raise XuiError(f"add inbound failed: {body.get('msg')}")
        return dict(body.get("obj") or {})

    async def add_client(
        self,
        *,
        inbound_id: int,
        client_uuid: str,
        email: str,
        sub_id: str,
        flow: str = "xtls-rprx-vision",
        total_bytes: int = 0,
        expiry_time: int = 0,
    ) -> None:
        await self.login()
        client = build_client_object(
            client_uuid=client_uuid,
            email=email,
            sub_id=sub_id,
            flow=flow,
            total_bytes=total_bytes,
            expiry_time=expiry_time,
        )
        body = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client]}),
        }
        response = await self._client.post("/panel/api/inbounds/addClient", json=body)
        response.raise_for_status()
        parsed = self._json(response)
        if not parsed.get("success"):
            raise XuiError(f"addClient failed: {parsed.get('msg')}")

    async def del_client(self, *, inbound_id: int, client_uuid: str) -> None:
        await self.login()
        response = await self._client.post(
            f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}"
        )
        response.raise_for_status()
        parsed = self._json(response)
        if not parsed.get("success"):
            msg = str(parsed.get("msg") or "")
            if "not found" in msg.lower():
                logger.info(
                    "del_client: client already absent, treating as success "
                    "inbound_id=%s uuid=%s msg=%r",
                    inbound_id,
                    client_uuid,
                    msg,
                )
                return
            # 3x-ui refuses to delete the last client in an inbound.
            # Add a temporary placeholder client first, then retry the deletion.
            if "no client remained" in msg.lower():
                logger.info(
                    "del_client: last client in inbound, adding placeholder and retrying "
                    "inbound_id=%s uuid=%s",
                    inbound_id,
                    client_uuid,
                )
                placeholder_uuid = str(uuid.uuid4())
                await self.add_client(
                    inbound_id=inbound_id,
                    client_uuid=placeholder_uuid,
                    email=f"_placeholder_{placeholder_uuid[:8]}",
                    sub_id=placeholder_uuid[:16],
                )
                retry_resp = await self._client.post(
                    f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}"
                )
                retry_resp.raise_for_status()
                retry_parsed = self._json(retry_resp)
                if not retry_parsed.get("success"):
                    retry_msg = str(retry_parsed.get("msg") or "")
                    if "not found" in retry_msg.lower():
                        return
                    raise XuiError(f"delClient retry failed: {retry_msg}")
                return
            raise XuiError(f"delClient failed: {msg}")

    async def get_client_traffics(self, email: str) -> Optional[Dict[str, Any]]:
        await self.login()
        response = await self._client.get(
            f"/panel/api/inbounds/getClientTraffics/{email}"
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        body = self._json(response)
        if not body.get("success"):
            return None
        obj = body.get("obj")
        if obj is None:
            return None
        return dict(obj)

    async def reset_client_traffic(self, *, inbound_id: int, email: str) -> None:
        await self.login()
        response = await self._client.post(
            f"/panel/api/inbounds/{inbound_id}/resetClientTraffic/{email}"
        )
        response.raise_for_status()

    async def new_x25519_cert(self) -> Optional[Dict[str, str]]:
        await self.login()
        # The new API path is /panel/api/server/getNewX25519Cert
        # We keep the old ones as fallbacks for compatibility.
        paths = (
            "/panel/api/server/getNewX25519Cert",
            "/panel/server/getNewX25519Cert",
            "/server/getNewX25519Cert",
        )
        for path in paths:
            try:
                response = await self._client.get(path)  # Doc says GET
                if response.status_code == 405:  # Method Not Allowed, try POST
                    response = await self._client.post(path)
            except httpx.HTTPError:
                continue
            if response.status_code == 404:
                continue
            try:
                body = self._json(response)
            except XuiError:
                continue
            obj = body.get("obj") or body
            if isinstance(obj, dict) and obj.get("publicKey") and obj.get("privateKey"):
                return {
                    "publicKey": str(obj["publicKey"]),
                    "privateKey": str(obj["privateKey"]),
                }
        return None

    async def update_client(
        self,
        *,
        inbound_id: int,
        client_uuid: str,
        email: str,
        sub_id: str,
        flow: str = "xtls-rprx-vision",
        total_bytes: int = 0,
        expiry_time: int = 0,
        enable: bool = True,
    ) -> None:
        await self.login()
        client = build_client_object(
            client_uuid=client_uuid,
            email=email,
            sub_id=sub_id,
            flow=flow,
            total_bytes=total_bytes,
            expiry_time=expiry_time,
        )
        client["enable"] = enable
        body = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client]}),
        }
        response = await self._client.post(
            f"/panel/api/inbounds/updateClient/{client_uuid}", json=body
        )
        response.raise_for_status()
        parsed = self._json(response)
        if not parsed.get("success"):
            raise XuiError(f"updateClient failed: {parsed.get('msg')}")

    async def del_inbound(self, inbound_id: int) -> None:
        await self.login()
        response = await self._client.post(f"/panel/api/inbounds/del/{inbound_id}")
        response.raise_for_status()
        parsed = self._json(response)
        if not parsed.get("success"):
            raise XuiError(f"del inbound failed: {parsed.get('msg')}")

    async def restart_xray(self) -> None:
        await self.login()
        response = await self._client.post("/panel/api/server/restartXrayService")
        response.raise_for_status()
        parsed = self._json(response)
        if not parsed.get("success"):
            raise XuiError(f"restart xray failed: {parsed.get('msg')}")

    async def panel_alive(self) -> bool:
        try:
            response = await self._client.get("/login", timeout=10.0)
            return 200 <= response.status_code < 500
        except httpx.HTTPError:
            return False

    @staticmethod
    def _json(response: httpx.Response) -> Dict[str, Any]:
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise XuiError(f"non-JSON response: {response.text[:200]!r}") from exc
        if not isinstance(data, dict):
            raise XuiError(f"unexpected response shape: {data!r}")
        return data
