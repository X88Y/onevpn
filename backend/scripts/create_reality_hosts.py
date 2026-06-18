"""Create Remnawave hosts with VLESS_TCP_REALITY for every Default-Profile node.

Usage:
    python create_reality_hosts.py                  # dry-run, prints actions
    python create_reality_hosts.py --apply          # actually applies changes to Remnawave
    python create_reality_hosts.py --env /path/.env # load a specific .env file
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from remnawave import RemnawaveSDK
from remnawave.enums import Fingerprint, SecurityLayer
from remnawave.models import CreateHostInboundData, CreateHostRequestDto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_PROFILE_UUID = UUID("00000000-0000-0000-0000-000000000000")
REALITY_INBOUND_UUID = UUID("9902c9e2-a74c-4576-973d-4d2e7f23a093")
REALITY_INBOUND_TAG = "VLESS_TCP_REALITY"
REALITY_SNI = "ads.x5.ru"
REALITY_PORT = 443
HOST_TAG = "SPEED_SERVER"

COUNTRY_MAP = {
    "DE": ("🇩🇪", "Германия"),
    "GB": ("🇬🇧", "Британия"),
    "PL": ("🇵🇱", "Польша"),
    "TR": ("🇹🇷", "Турция"),
    "HU": ("🇭🇺", "Венгрия"),
    "NL": ("🇳🇱", "Нидерланды"),
    "RU": ("🇷🇺", "Россия"),
    "BY": ("🇧🇾", "Беларусь"),
}


def _load_env(env_path: Optional[str] = None) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    if env_path:
        load_dotenv(env_path, override=True)
        return

    candidates = [
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent / "server_manager" / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p, override=True)
            return


def get_flag_emoji(country_code: str) -> str:
    if not country_code or len(country_code) != 2:
        return "🌐"
    return "".join(chr(127397 + ord(c.upper())) for c in country_code)


def determine_host_name(node, existing_hosts_for_node: list) -> str:
    """Derive a Reality host remark from existing non-Reality hosts on the node."""
    skip_keywords = ["Моб.", "резерв", "ТикТок", "Доступ", "💎", "📱", "⚡", "🇧🇹", "Reality", "Hysteria"]

    clean_hosts = []
    for h in existing_hosts_for_node:
        if any(keyword in h.remark for keyword in skip_keywords):
            continue
        clean_hosts.append(h)

    if clean_hosts:
        clean_hosts.sort(key=lambda x: len(x.remark))
        base_name = clean_hosts[0].remark.strip()
        return f"{base_name} Reality"

    non_reality_hosts = [h for h in existing_hosts_for_node if "Reality" not in h.remark]
    if non_reality_hosts:
        non_reality_hosts.sort(key=lambda x: len(x.remark))
        base_name = non_reality_hosts[0].remark.strip()
        return f"{base_name} Reality"

    cc = (node.country_code or "").upper()
    if cc in COUNTRY_MAP:
        flag, country_name = COUNTRY_MAP[cc]
        return f"{flag} {country_name} Reality"

    flag = get_flag_emoji(cc)
    return f"{flag} {node.name} Reality"


def _find_reality_inbound(node):
    cp = node.config_profile
    if not cp or not cp.active_inbounds:
        return None
    if cp.active_config_profile_uuid != DEFAULT_PROFILE_UUID:
        return None
    for ib in cp.active_inbounds:
        if ib.tag == REALITY_INBOUND_TAG:
            return ib
    return None


async def run_creation(*, apply: bool, env_path: Optional[str] = None) -> None:
    _load_env(env_path)

    remnawave_base = os.getenv("REMNAWAVE_BASE_URL") or os.getenv("REMNAWAVE_URL")
    remnawave_token = os.getenv("REMNAWAVE_API_TOKEN") or os.getenv("REMNAWAVE_TOKEN")

    if not remnawave_base or not remnawave_token:
        logger.error(
            "REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN must be set "
            "(via environment or .env file)"
        )
        sys.exit(1)

    sdk = RemnawaveSDK(base_url=remnawave_base, token=remnawave_token)

    logger.info("Fetching nodes from Remnawave...")
    try:
        nodes = await sdk.nodes.get_all_nodes()
    except Exception as e:
        logger.error(f"Failed to fetch nodes from Remnawave: {e}")
        sys.exit(1)

    logger.info("Fetching existing hosts from Remnawave...")
    try:
        existing_hosts = await sdk.hosts.get_all_hosts()
    except Exception as e:
        logger.error(f"Failed to fetch hosts from Remnawave: {e}")
        sys.exit(1)

    reality_nodes: List = []
    for node in nodes:
        inbound = _find_reality_inbound(node)
        if inbound:
            reality_nodes.append((node, inbound))

    logger.info(
        f"Found {len(reality_nodes)} Default-Profile nodes with {REALITY_INBOUND_TAG}."
    )

    created_count = 0
    skipped_count = 0

    for node, inbound in reality_nodes:
        existing_host = None
        for h in existing_hosts:
            if not h.inbound:
                continue
            if h.inbound.config_profile_inbound_uuid != REALITY_INBOUND_UUID:
                continue
            if node.uuid in h.nodes or h.address == node.address:
                existing_host = h
                break

        if existing_host:
            logger.info(
                f"[-] Node {node.name} ({node.address}) already has Reality host: "
                f"remark='{existing_host.remark}' (Skipping)"
            )
            skipped_count += 1
            continue

        hosts_for_node = [h for h in existing_hosts if node.uuid in h.nodes]
        remark = determine_host_name(node, hosts_for_node)

        if apply:
            logger.info(
                f"[+] Creating Reality host for node {node.name} ({node.address}): "
                f"remark='{remark}', port={REALITY_PORT}, SNI='{REALITY_SNI}'..."
            )
            try:
                inbound_data = CreateHostInboundData(
                    config_profile_uuid=DEFAULT_PROFILE_UUID,
                    config_profile_inbound_uuid=inbound.uuid,
                )

                req_dto = CreateHostRequestDto(
                    inbound=inbound_data,
                    remark=remark,
                    address=node.address,
                    port=REALITY_PORT,
                    sni=REALITY_SNI,
                    host="",
                    fingerprint=Fingerprint.CHROME,
                    tag=HOST_TAG,
                    nodes=[node.uuid],
                    security_layer=SecurityLayer.DEFAULT,
                    is_hidden=False,
                    override_sni_from_address=False,
                    keep_blank_sni=False,
                )

                await sdk.hosts.create_host(req_dto)
                logger.info(f"    Successfully created host: '{remark}'")
                created_count += 1
            except Exception as e:
                logger.error(f"    Failed to create host '{remark}': {e}")
        else:
            logger.info(
                f"[DRY-RUN] Would create Reality host for node {node.name} ({node.address}):"
            )
            logger.info(f"    Remark:          '{remark}'")
            logger.info(f"    Address/Port:    {node.address}:{REALITY_PORT}")
            logger.info(f"    Inbound:         {inbound.tag} (UUID: {inbound.uuid})")
            logger.info(f"    SNI:             '{REALITY_SNI}'")
            logger.info(f"    Tag:             '{HOST_TAG}'")
            created_count += 1

    logger.info("\nExecution summary:")
    logger.info(f"  Processed: {len(reality_nodes)} nodes")
    if apply:
        logger.info(f"  Created:   {created_count} hosts")
    else:
        logger.info(f"  Would create: {created_count} hosts")
    logger.info(f"  Skipped:   {skipped_count} hosts")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create Remnawave hosts with VLESS_TCP_REALITY for every Default-Profile node."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply changes to Remnawave (default is dry-run only)",
    )
    parser.add_argument(
        "--env",
        metavar="FILE",
        default=None,
        help="Path to a .env file to load (default: auto-detect)",
    )
    args = parser.parse_args()

    asyncio.run(run_creation(apply=args.apply, env_path=args.env))


if __name__ == "__main__":
    main()
