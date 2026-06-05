"""Replace VLESS-TCP-Reality inbound with VLESS-TCP-TLS inbound (port 9443) on all Remnawave hosts.

Usage:
    python replace_reality_with_tls.py                  # dry-run, prints actions
    python replace_reality_with_tls.py --apply          # actually applies changes to Remnawave
    python replace_reality_with_tls.py --env /path/.env # load a specific .env file
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

from remnawave import RemnawaveSDK
from remnawave.models import UpdateHostRequestDto, CreateHostInboundData

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

REALITY_INBOUND_UUID = UUID("9902c9e2-a74c-4576-973d-4d2e7f23a093")
TLS_INBOUND_UUID = UUID("9794bbf9-868b-41c7-9cd8-f75b52d608bc")
PROFILE_UUID = UUID("00000000-0000-0000-0000-000000000000")
TARGET_PORT = 9443

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

async def run_update(*, apply: bool, env_path: Optional[str] = None) -> None:
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

    # Fetch existing hosts from Remnawave
    logger.info("Fetching hosts from Remnawave...")
    try:
        hosts = await sdk.hosts.get_all_hosts()
    except Exception as e:
        logger.error(f"Failed to fetch hosts from Remnawave: {e}")
        sys.exit(1)

    logger.info(f"Fetched {len(hosts)} hosts.")

    target_hosts = []
    for h in hosts:
        if h.inbound and h.inbound.config_profile_inbound_uuid == REALITY_INBOUND_UUID:
            target_hosts.append(h)

    logger.info(f"Found {len(target_hosts)} hosts using VLESS_TCP_REALITY.")

    if not target_hosts:
        logger.info("No hosts found using VLESS_TCP_REALITY. Exiting.")
        return

    updated_count = 0

    for h in target_hosts:
        if apply:
            logger.info(f"[+] Updating host '{h.remark}' ({h.uuid}) to VLESS_TCP_TLS (port {TARGET_PORT})...")
            try:
                new_inbound = CreateHostInboundData(
                    config_profile_uuid=PROFILE_UUID,
                    config_profile_inbound_uuid=TLS_INBOUND_UUID
                )
                update_dto = UpdateHostRequestDto(
                    uuid=h.uuid,
                    inbound=new_inbound,
                    port=TARGET_PORT
                )
                await sdk.hosts.update_host(update_dto)
                logger.info(f"    Successfully updated host '{h.remark}'")
                updated_count += 1
            except Exception as e:
                logger.error(f"    Failed to update host '{h.remark}': {e}")
        else:
            logger.info(f"[DRY-RUN] Would update host '{h.remark}' ({h.uuid}):")
            logger.info(f"    From Inbound: {REALITY_INBOUND_UUID} (Port {h.port})")
            logger.info(f"    To Inbound:   {TLS_INBOUND_UUID} (Port {TARGET_PORT})")
            updated_count += 1

    logger.info(f"\nExecution summary:")
    logger.info(f"  Total hosts matching VLESS_TCP_REALITY: {len(target_hosts)}")
    if apply:
        logger.info(f"  Successfully updated:                  {updated_count} hosts")
    else:
        logger.info(f"  Would update:                           {updated_count} hosts")

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replace VLESS-TCP-Reality inbound with VLESS-TCP-TLS inbound on all Remnawave hosts."
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
    
    asyncio.run(run_update(apply=args.apply, env_path=args.env))

if __name__ == "__main__":
    main()
