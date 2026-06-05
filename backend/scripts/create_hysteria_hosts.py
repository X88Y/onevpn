"""Create Remnawave hosts with Hysteria protocol for every server node that has a Hysteria inbound.

Usage:
    python create_hysteria_hosts.py                  # dry-run, prints actions
    python create_hysteria_hosts.py --apply          # actually applies changes to Remnawave
    python create_hysteria_hosts.py --env /path/.env # load a specific .env file
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID

from remnawave import RemnawaveSDK
from remnawave.models import CreateHostRequestDto, CreateHostInboundData
from remnawave.enums import SecurityLayer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

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

# ---------------------------------------------------------------------------
# Bootstrap: load .env so this script can be run standalone
# ---------------------------------------------------------------------------
def _load_env(env_path: Optional[str] = None) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    if env_path:
        load_dotenv(env_path, override=True)
        return

    # Walk up looking for .env
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
    """Helper to convert standard 2-letter country code to flag emoji."""
    if not country_code or len(country_code) != 2:
        return "🌐"
    return "".join(chr(127397 + ord(c.upper())) for c in country_code)

def determine_host_name(node, existing_hosts_for_node: list) -> str:
    """Determine the best name for the new Hysteria host."""
    # Try to extract the base name from existing non-Hysteria hosts
    clean_hosts = []
    for h in existing_hosts_for_node:
        if "Hysteria" in h.remark:
            continue
        # Filter out special tags/promos (e.g. bypass, backup, TikTok, etc.)
        if any(keyword in h.remark for keyword in ["Моб.", "резерв", "ТикТок", "Доступ", "💎", "📱", "⚡", "🇧🇹"]):
            continue
        clean_hosts.append(h)
    
    if clean_hosts:
        # Sort by length to get the shortest/cleanest one (e.g., "🇩🇪 Германия 2")
        clean_hosts.sort(key=lambda x: len(x.remark))
        base_name = clean_hosts[0].remark.strip()
        return f"{base_name} Hysteria"
        
    # If no clean hosts but other hosts exist, just pick the shortest one
    non_hysteria_hosts = [h for h in existing_hosts_for_node if "Hysteria" not in h.remark]
    if non_hysteria_hosts:
        non_hysteria_hosts.sort(key=lambda x: len(x.remark))
        base_name = non_hysteria_hosts[0].remark.strip()
        return f"{base_name} Hysteria"
        
    # Fallback to country mapping or node name
    cc = (node.country_code or "").upper()
    if cc in COUNTRY_MAP:
        flag, country_name = COUNTRY_MAP[cc]
        return f"{flag} {country_name} Hysteria"
        
    flag = get_flag_emoji(cc)
    return f"{flag} {node.name} Hysteria"

async def run_creation(*, apply: bool, env_path: Optional[str] = None) -> None:
    _load_env(env_path)

    # Remnawave Config
    remnawave_base = os.getenv("REMNAWAVE_BASE_URL") or os.getenv("REMNAWAVE_URL")
    remnawave_token = os.getenv("REMNAWAVE_API_TOKEN") or os.getenv("REMNAWAVE_TOKEN")

    if not remnawave_base or not remnawave_token:
        logger.error(
            "REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN must be set "
            "(via environment or .env file)"
        )
        sys.exit(1)

    sdk = RemnawaveSDK(base_url=remnawave_base, token=remnawave_token)

    # Fetch nodes from Remnawave
    logger.info("Fetching nodes from Remnawave...")
    try:
        nodes = await sdk.nodes.get_all_nodes()
    except Exception as e:
        logger.error(f"Failed to fetch nodes from Remnawave: {e}")
        sys.exit(1)

    logger.info(f"Fetched {len(nodes)} nodes.")

    # Fetch existing hosts from Remnawave
    logger.info("Fetching existing hosts from Remnawave...")
    try:
        existing_hosts = await sdk.hosts.get_all_hosts()
    except Exception as e:
        logger.error(f"Failed to fetch hosts from Remnawave: {e}")
        sys.exit(1)

    logger.info(f"Fetched {len(existing_hosts)} existing hosts.")

    # Identify nodes with Hysteria inbound
    hysteria_nodes = []
    node_to_hysteria_inbound = {}

    for node in nodes:
        cp = node.config_profile
        if not cp or not cp.active_inbounds:
            continue
        for ib in cp.active_inbounds:
            if ib.type == "hysteria" or (ib.raw_inbound and ib.raw_inbound.get("protocol") == "hysteria"):
                hysteria_nodes.append(node)
                node_to_hysteria_inbound[node.uuid] = ib
                break

    logger.info(f"Found {len(hysteria_nodes)} nodes with Hysteria inbounds.")

    created_count = 0
    skipped_count = 0

    for node in hysteria_nodes:
        inbound = node_to_hysteria_inbound[node.uuid]
        
        # Check if Hysteria host already exists for this node and inbound
        existing_host = None
        for h in existing_hosts:
            if h.inbound and h.inbound.config_profile_inbound_uuid == inbound.uuid:
                if node.uuid in h.nodes or h.address == node.address:
                    existing_host = h
                    break
        
        if existing_host:
            logger.info(f"[-] Node {node.name} ({node.address}) already has Hysteria host: remark='{existing_host.remark}' (Skipping)")
            skipped_count += 1
            continue

        # Get existing hosts for this node to determine name
        hosts_for_node = [h for h in existing_hosts if node.uuid in h.nodes]
        remark = determine_host_name(node, hosts_for_node)

        # Hysteria settings:
        # We use standard Hysteria settings similar to the existing 🇭🇺Hysteria host
        port = int(inbound.port)
        sni = "xn--80aksgi6f.xn----ctbzfboapgel4j.xn--p1ai"
        tag = "SPEED_SERVER"

        if apply:
            logger.info(f"[+] Creating Hysteria host for node {node.name} ({node.address}): remark='{remark}', port={port}, SNI='{sni}'...")
            try:
                inbound_data = CreateHostInboundData(
                    config_profile_uuid=node.config_profile.active_config_profile_uuid,
                    config_profile_inbound_uuid=inbound.uuid
                )
                
                req_dto = CreateHostRequestDto(
                    inbound=inbound_data,
                    remark=remark,
                    address=node.address,
                    port=port,
                    path=None,
                    sni=sni,
                    host="",
                    tag=tag,
                    nodes=[node.uuid],
                    excluded_internal_squads=[],
                    exclude_from_subscription_types=[],
                    is_disabled=False,
                    is_hidden=False,
                    override_sni_from_address=False,
                    keep_blank_sni=False,
                    security_layer=SecurityLayer.DEFAULT
                )
                
                await sdk.hosts.create_host(req_dto)
                logger.info(f"    Successfully created host: '{remark}'")
                created_count += 1
            except Exception as e:
                logger.error(f"    Failed to create host '{remark}': {e}")
        else:
            logger.info(f"[DRY-RUN] Would create Hysteria host for node {node.name} ({node.address}):")
            logger.info(f"    Remark:          '{remark}'")
            logger.info(f"    Address/Port:    {node.address}:{port}")
            logger.info(f"    Inbound:         {inbound.tag} (UUID: {inbound.uuid})")
            logger.info(f"    SNI:             '{sni}'")
            logger.info(f"    Tag:             '{tag}'")
            created_count += 1

    logger.info(f"\nExecution summary:")
    logger.info(f"  Processed: {len(hysteria_nodes)} nodes")
    if apply:
        logger.info(f"  Created:   {created_count} hosts")
    else:
        logger.info(f"  Would create: {created_count} hosts")
    logger.info(f"  Skipped:   {skipped_count} hosts")

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create Remnawave hosts with Hysteria protocol for every server node."
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
