"""Periodic 3x-ui panel health probe.

Flips `vpn_servers/{id}.status` between `healthy` and `error` based on whether
the panel responds to a `GET /login`. `provisioning` and `disabled` statuses
are left alone — the install worker and admin actions own those.

Also backfills missing `countryCode` for healthy servers via a lightweight
GeoIP lookup.
"""

import asyncio
import logging
import socket
from typing import List, Optional

import httpx
from firebase_admin import firestore

from server_manager.config import settings
from server_manager.firestore_client import VPN_SERVERS_COLLECTION, init_firestore
from server_manager.xui.client import XuiClient, server_from_doc

logger = logging.getLogger(__name__)

_MANAGED_STATUSES = {"healthy", "error"}

_COUNTRY_CODE_TO_RU = {
    "AD": "Андорра",
    "AE": "ОАЭ",
    "AL": "Албания",
    "AM": "Армения",
    "AR": "Аргентина",
    "AT": "Австрия",
    "AU": "Австралия",
    "AZ": "Азербайджан",
    "BA": "Босния и Герцеговина",
    "BE": "Бельгия",
    "BG": "Болгария",
    "BR": "Бразилия",
    "BY": "Беларусь",
    "CA": "Канада",
    "CH": "Швейцария",
    "CL": "Чили",
    "CO": "Колумбия",
    "CY": "Кипр",
    "CZ": "Чехия",
    "DE": "Германия",
    "DK": "Дания",
    "EE": "Эстония",
    "ES": "Испания",
    "FI": "Финляндия",
    "FR": "Франция",
    "GB": "Великобритания",
    "GE": "Грузия",
    "GR": "Греция",
    "HK": "Гонконг",
    "HR": "Хорватия",
    "HU": "Венгрия",
    "ID": "Индонезия",
    "IE": "Ирландия",
    "IL": "Израиль",
    "IN": "Индия",
    "IS": "Исландия",
    "IT": "Италия",
    "JP": "Япония",
    "KZ": "Казахстан",
    "KR": "Корея",
    "LT": "Литва",
    "LU": "Люксембург",
    "LV": "Латвия",
    "MD": "Молдова",
    "ME": "Черногория",
    "MK": "Северная Македония",
    "MT": "Мальта",
    "MX": "Мексика",
    "MY": "Малайзия",
    "NL": "Нидерланды",
    "NO": "Норвегия",
    "NZ": "Новая Зеландия",
    "PE": "Перу",
    "PH": "Филиппины",
    "PL": "Польша",
    "PT": "Португалия",
    "RO": "Румыния",
    "RS": "Сербия",
    "RU": "Россия",
    "SE": "Швеция",
    "SG": "Сингапур",
    "SI": "Словения",
    "SK": "Словакия",
    "TH": "Таиланд",
    "TR": "Турция",
    "TW": "Тайвань",
    "UA": "Украина",
    "US": "США",
    "UZ": "Узбекистан",
    "VN": "Вьетнам",
    "ZA": "ЮАР",
}


def _ru_country_name(code: str) -> Optional[str]:
    return _COUNTRY_CODE_TO_RU.get((code or "").upper())


async def _detect_country_code(ip_or_host: str) -> Optional[str]:
    """Lightweight GeoIP lookup using ip-api.com. Returns ISO country code or None."""
    ip = ip_or_host.strip()
    if not ip.replace(".", "").isdigit():
        try:
            ip = socket.gethostbyname(ip)
        except Exception:  # noqa: BLE001
            return None
    parts = ip.split(".")
    if len(parts) == 4 and parts[0].isdigit():
        first_octet = int(parts[0])
        second_octet = int(parts[1]) if parts[1].isdigit() else 0
        if first_octet in (10, 127) or (first_octet == 172 and 16 <= second_octet <= 31) or (first_octet == 192 and second_octet == 168):
            return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,countryCode"},
            )
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "success":
                return str(data.get("countryCode") or "").strip() or None
    except Exception:  # noqa: BLE001
        logger.debug("ip-api lookup failed for %s", ip_or_host, exc_info=True)
    return None


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

    updates: dict = {}

    # Backfill missing countryCode / label for healthy servers
    if healthy and (not data.get("countryCode") or not data.get("label")):
        host = data.get("serverPublicHost") or data.get("host")
        if host:
            detected = await _detect_country_code(str(host))
            if detected:
                updates["countryCode"] = detected.upper()
                if not data.get("label"):
                    ru_name = _ru_country_name(detected)
                    if ru_name:
                        updates["label"] = ru_name

    new_status = "healthy" if healthy else "error"
    if new_status != current:
        updates["status"] = new_status

    if updates:
        updates["lastHealthAt"] = firestore.SERVER_TIMESTAMP
        updates["updatedAt"] = firestore.SERVER_TIMESTAMP
        await asyncio.to_thread(snap.reference.update, updates)
        if "status" in updates:
            logger.info("server %s status %s -> %s", snap.id, current, new_status)
        if "countryCode" in updates:
            logger.info("server %s countryCode backfilled -> %s", snap.id, updates["countryCode"])
    elif healthy:
        # Even if status didn't change, update lastHealthAt for healthy servers
        await asyncio.to_thread(
            snap.reference.update,
            {
                "lastHealthAt": firestore.SERVER_TIMESTAMP,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
        )


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
