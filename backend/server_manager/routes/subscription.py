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
import json
import logging
import time
import urllib.parse
from typing import List, Tuple

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

# Common label substrings mapped to ISO 3166-1 alpha-2 country codes.
# Used as a fallback when a server document has no explicit `countryCode`.
_LABEL_TO_COUNTRY_CODE = {
    "germany": "DE",
    "deutschland": "DE",
    "usa": "US",
    "united states": "US",
    "uk": "GB",
    "united kingdom": "GB",
    "britain": "GB",
    "england": "GB",
    "france": "FR",
    "netherlands": "NL",
    "holland": "NL",
    "russia": "RU",
    "russian": "RU",
    "finland": "FI",
    "estonia": "EE",
    "sweden": "SE",
    "norway": "NO",
    "poland": "PL",
    "turkey": "TR",
    "turkiye": "TR",
    "singapore": "SG",
    "japan": "JP",
    "korea": "KR",
    "india": "IN",
    "brazil": "BR",
    "canada": "CA",
    "australia": "AU",
    "spain": "ES",
    "italy": "IT",
    "switzerland": "CH",
    "austria": "AT",
    "czech": "CZ",
    "romania": "RO",
    "bulgaria": "BG",
    "hungary": "HU",
    "latvia": "LV",
    "lithuania": "LT",
    "moldova": "MD",
    "ukraine": "UA",
    "belarus": "BY",
    "kazakhstan": "KZ",
    "armenia": "AM",
    "georgia": "GE",
    "azerbaijan": "AZ",
    "israel": "IL",
    "uae": "AE",
    "dubai": "AE",
    "south africa": "ZA",
    "mexico": "MX",
    "argentina": "AR",
    "chile": "CL",
    "colombia": "CO",
    "peru": "PE",
    "venezuela": "VE",
    "hong kong": "HK",
    "taiwan": "TW",
    "thailand": "TH",
    "vietnam": "VN",
    "malaysia": "MY",
    "indonesia": "ID",
    "philippines": "PH",
    "new zealand": "NZ",
    "ireland": "IE",
    "denmark": "DK",
    "belgium": "BE",
    "portugal": "PT",
    "greece": "GR",
    "slovenia": "SI",
    "slovakia": "SK",
    "croatia": "HR",
    "serbia": "RS",
    "bosnia": "BA",
    "albania": "AL",
    "north macedonia": "MK",
    "macedonia": "MK",
    "montenegro": "ME",
    "luxembourg": "LU",
    "malta": "MT",
    "cyprus": "CY",
    "iceland": "IS",
    "liechtenstein": "LI",
}


def _country_code_to_flag(code: str) -> str:
    """Convert a 2-letter ISO country code to a flag emoji."""
    code = code.upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)


def _get_server_flag_and_name(server_data: dict) -> Tuple[str, str]:
    """Returns (flag_emoji, display_name) for a server."""
    # 1. Explicit countryCode field
    country_code = (server_data.get("countryCode") or "").strip()
    if country_code:
        flag = _country_code_to_flag(country_code)
        name = (
            (server_data.get("label") or "").strip()
            or (server_data.get("serverPublicHost") or server_data.get("host") or "Server")
        )
        return flag, name

    # 2. Try to infer from label
    label = (server_data.get("label") or "").strip()
    if label:
        label_lower = label.lower()
        for key, code in _LABEL_TO_COUNTRY_CODE.items():
            if key in label_lower:
                flag = _country_code_to_flag(code)
                return flag, label

    # 3. Fallback: label or host, no flag
    name = label or (server_data.get("serverPublicHost") or server_data.get("host") or "Server")
    return "", name


def _rewrite_url_remark(url: str, display_name: str) -> str:
    """Replace the fragment (#remark) of a vless/vmess/ss/trojan URL."""
    if "#" in url:
        base, _ = url.rsplit("#", 1)
    else:
        base = url
    encoded_name = urllib.parse.quote(display_name, safe="")
    return f"{base}#{encoded_name}"


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
) -> Tuple[dict, List[str]]:
    public_host = server_data.get("serverPublicHost") or server_data.get("host")
    sub_port = server_data.get("subPort")
    if not public_host or not sub_port:
        return server_data, []
    url = f"https://{public_host}:{sub_port}/sub/{sub_id}"
    try:
        response = await http.get(url, timeout=15.0)
    except httpx.HTTPError as exc:
        logger.info("subscription fetch failed url=%s: %s", url, exc)
        return server_data, []
    if response.status_code != 200:
        return server_data, []
    decoded = _try_b64_decode(response.text)
    return server_data, [line.strip() for line in decoded.splitlines() if line.strip()]


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
    for server_data, lines in results:
        flag, location_name = _get_server_flag_and_name(server_data)
        display_name = f"{flag} {location_name}".strip() if flag else location_name
        for line in lines:
            if line in seen:
                continue
            seen.add(line)
            rewritten = _rewrite_url_remark(line, display_name)
            merged.append(rewritten)

    # Happ Routing Profile
    # Documentation: https://www.happ.su/main/dev-docs/routing
    routing_profile = {
        "Name": "MVM-RU",
        "GlobalProxy": True,
        "RemoteDNSType": "DoH",
        "RemoteDNSDomain": "https://8.8.8.8/dns-query",
        "RemoteDNSIP": "8.8.8.8",
        "DomesticDNSType": "DoH",
        "DomesticDNSDomain": "https://77.88.8.8/dns-query",
        "DomesticDNSIP": "77.88.8.8",
        "DnsHosts": {
            "lkfl2.nalog.ru": "213.24.64.175",
            "lknpd.nalog.ru": "213.24.64.181",
        },
        "Geoipurl": "https://cdn.jsdelivr.net/gh/hydraponique/roscomvpn-geoip@202604250521/release/geoip.dat",
        "Geositeurl": "https://cdn.jsdelivr.net/gh/hydraponique/roscomvpn-geosite@202604152235/release/geosite.dat",
        "DirectSites": [
            "geosite:private",
            "geosite:category-ru",
            "geosite:whitelist",
            "geosite:microsoft",
            "geosite:apple",
            "geosite:epicgames",
            "geosite:riot",
            "geosite:escapefromtarkov",
            "geosite:steam",
            "geosite:twitch",
            "geosite:pinterest",
            "geosite:faceit",
        ],
        "ProxySites": [
            "geosite:google-play",
            "geosite:github",
            "geosite:twitch-ads",
            "geosite:youtube",
            "geosite:telegram",
        ],
        "BlockSites": [
            "geosite:win-spy",
            "geosite:torrent",
            "geosite:category-ads",
        ],
        "DirectIp": ["geoip:private", "geoip:direct"],
        "ProxyIp": [],
        "BlockIp": [],
        "DomainStrategy": "IPIfNonMatch",
        "FakeDNS": False,
        "UseChunkFiles": True,
        "RouteOrder": "block-proxy-direct",
        "LastUpdated": 1777094515,
    }
    routing_json = json.dumps(routing_profile, separators=(",", ":"), ensure_ascii=False)
    routing_b64 = base64.urlsafe_b64encode(routing_json.encode()).decode().rstrip("=")

    # Add traffic info if available
    client_data = client_snap.to_dict() or {}
    up = client_data.get("up", 0)
    down = client_data.get("down", 0)
    total = client_data.get("total", 0)

    # Fetch user data for expiration
    user_uid = client_snap.id
    user_snap = db.collection("users").document(user_uid).get()
    expire_ts = 0
    if user_snap.exists:
        user_data = user_snap.to_dict() or {}
        if expire_at := user_data.get("subscriptionEndsAt"):
            if hasattr(expire_at, "timestamp"):
                expire_ts = int(expire_at.timestamp())

    now_ts = int(time.time())
    is_expired = expire_ts > 0 and expire_ts <= now_ts

    if is_expired:
        merged = []
        profile_title = "Ваша подписка истекла VK: mvmvpn"
        support_url = "https://m.vk.com/write-199074445"
        profile_web_page_url = "https://m.vk.com/write-199074445"
        announce = "Ваша подписка истекла VK: mvmvpn"
    else:
        profile_title = "MVM Vpn"
        support_url = "https://t.me/MVM_Support"
        profile_web_page_url = ""
        announce = ""

    # Metadata headers for Happ and other compatible apps
    # Documentation: https://www.happ.su/main/dev-docs/app-management
    headers_lines = [
        f"#profile-title: {profile_title}",
        "#profile-update-interval: 1",
        f"#support-url: {support_url}",
    ]
    if profile_web_page_url:
        headers_lines.append(f"#profile-web-page-url: {profile_web_page_url}")
    if announce:
        headers_lines.append(f"#announce: {announce}")
    headers_lines.append(f"happ://routing/onadd/{routing_b64}")

    sub_info = f"#subscription-userinfo: upload={up}; download={down}; total={total}; expire={expire_ts}"
    headers_lines.append(sub_info)

    body = "\n".join(headers_lines + merged) + ("\n" if merged else "")
    payload = base64.b64encode(body.encode("utf-8")).decode("ascii")
    response_headers = {
        "Profile-Update-Interval": "1",
        "Subscription-UserInfo": sub_info.lstrip("#"),
        "Content-Disposition": f'inline; filename="mvm-{sub_id[:8]}"',
        "Support-Url": support_url,
    }
    if profile_web_page_url:
        response_headers["Profile-Web-Page-Url"] = profile_web_page_url
    if announce and announce.isascii():
        response_headers["Announce"] = announce

    return Response(
        content=payload,
        media_type="text/plain; charset=utf-8",
        headers=response_headers,
    )
