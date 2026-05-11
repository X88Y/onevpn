"""Inbound and client templates for 3x-ui (MHSanaei) panel."""

import json


def random_inbound_port() -> int:
    return 443


def build_default_vless_reality_payload(
    *,
    port: int,
    private_key: str,
    public_key: str,
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
            "xver": 0,
            "target": "www.tradingview.com:443",
            "serverNames": [
                "www.tradingview.com",
                "tradingview.com"
            ],
            "privateKey": private_key,
            "minClientVer": "",
            "maxClientVer": "",
            "maxTimediff": 0,
            "shortIds": [
            "9c33a6",
            "cf59"
            ],
            "mldsa65Seed": "",
            "settings": {
            "publicKey": public_key,
            "fingerprint": "chrome",
            "serverName": "",
            "spiderX": "/",
            "mldsa65Verify": ""
            }
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
        "destOverride": [
            "http",
            "tls"
        ],
        "metadataOnly": False,
        "routeOnly": False
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
    total_bytes: int = 0,
    expiry_time: int = 0,
) -> Dict[str, Any]:
    """Build a client object for the 3x-ui API.
    
    Note: 'totalGB' in the 3x-ui API actually refers to total traffic in bytes.
    """
    return {
        "id": client_uuid,
        "flow": flow,
        "email": email,
        "limitIp": 0,
        "totalGB": total_bytes,
        "expiryTime": expiry_time,
        "enable": True,
        "tgId": "",
        "subId": sub_id,
        "reset": 0,
    }
