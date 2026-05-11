"""Default VLESS+XHTTP inbound template used when a server has none yet."""

import json
from typing import Any, Dict, List, Optional


def random_inbound_port() -> int:
    return 443


def build_default_vless_reality_payload(
    *,
    port: int,
    private_key: str,
    remark: str = "mvm-default",
    initial_clients: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build the JSON payload accepted by `POST /panel/api/inbounds/add`.

    Uses VLESS over TCP with REALITY. The 3x-ui API expects
    `settings`, `streamSettings`, and `sniffing` as JSON-encoded strings.
    """
    settings = {
        "clients": initial_clients or [],
        "decryption": "none",
        "fallbacks": [],
    }
    stream_settings = {
        "network": "tcp",
        "security": "reality",
        "externalProxy": [],
        "realitySettings": {
            "show": False,
            "dest": "tradingview.com:443",
            "xver": 0,
            "serverNames": [
                "tradingview.com"
            ],
            "privateKey": private_key,
            "minClientVer": "",
            "maxClientVer": "",
            "maxTimeDiff": 0,
            "shortIds": [
                ""
            ]
        },
        "tcpSettings": {
            "acceptProxyProtocol": False,
            "header": {
                "type": "none"
            }
        }
    }
    sniffing = {
        "enabled": True,
        "destOverride": ["http", "tls"],
        "metadataOnly": False,
        "routeOnly": False,
    }
    return {
        "up": 0,
        "down": 0,
        "total": 0,
        "remark": remark,
        "enable": True,
        "expiryTime": 0,
        "listen": "",
        "port": port,
        "protocol": "vless",
        "settings": json.dumps(settings),
        "streamSettings": json.dumps(stream_settings),
        "sniffing": json.dumps(sniffing),
    }


def build_client_object(
    *,
    client_uuid: str,
    email: str,
    sub_id: str,
    flow: str = "",
    total_gb: int = 0,
    expiry_time: int = 0,
) -> Dict[str, Any]:
    return {
        "id": client_uuid,
        "flow": flow,
        "email": email,
        "limitIp": 0,
        "totalGB": total_gb,
        "expiryTime": expiry_time,
        "enable": True,
        "tgId": "",
        "subId": sub_id,
        "reset": 0,
    }
