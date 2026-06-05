"""Sync xHTTP settings from config profile inbounds to Remnawave hosts.

This script fetches all hosts and inbounds from Remnawave, identifies hosts that use
the xHTTP protocol, checks if their 'path' and 'x_http_extra_params' match the settings
defined in their associated config profile inbounds, and syncs them if they are mismatched.

Usage:
    python sync_xhttp.py                  # dry-run, prints actions
    python sync_xhttp.py --apply          # actually applies changes to Remnawave
    python sync_xhttp.py --env /path/.env # load a specific .env file
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


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


async def sync_hosts(*, apply: bool, env_path: Optional[str] = None) -> None:
    _load_env(env_path)

    base_url = os.getenv("REMNAWAVE_BASE_URL") or os.getenv("REMNAWAVE_URL")
    api_token = os.getenv("REMNAWAVE_API_TOKEN") or os.getenv("REMNAWAVE_TOKEN")

    if not base_url or not api_token:
        logger.error(
            "REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN must be set "
            "(via environment or .env file)"
        )
        sys.exit(1)

    try:
        from remnawave import RemnawaveSDK
        from remnawave.models import UpdateHostRequestDto
    except ImportError:
        logger.error("remnawave SDK not installed. Run: pip install remnawave")
        sys.exit(1)

    sdk = RemnawaveSDK(base_url=base_url, token=api_token)

    # 1. Fetch inbounds
    logger.info("Fetching inbounds from Remnawave...")
    try:
        inbounds_resp = await sdk.inbounds.get_all_inbounds()
        inbounds = {ib.uuid: ib for ib in inbounds_resp.inbounds}
        logger.info(f"Found {len(inbounds)} inbounds.")
    except Exception as e:
        logger.error(f"Failed to fetch inbounds from Remnawave: {e}")
        sys.exit(1)

    # 2. Fetch hosts
    logger.info("Fetching hosts from Remnawave...")
    try:
        hosts_resp = await sdk.hosts.get_all_hosts()
        hosts = list(hosts_resp)
        logger.info(f"Found {len(hosts)} hosts.")
    except Exception as e:
        logger.error(f"Failed to fetch hosts from Remnawave: {e}")
        sys.exit(1)

    # 3. Process hosts
    total_checked = 0
    mismatched_count = 0
    success_count = 0
    fail_count = 0

    for host in hosts:
        inbound_uuid = host.inbound.config_profile_inbound_uuid
        if not inbound_uuid:
            continue

        if inbound_uuid not in inbounds:
            logger.warning(
                f"Host '{host.remark}' ({host.uuid}) references unknown inbound UUID: {inbound_uuid}"
            )
            continue

        ib = inbounds[inbound_uuid]
        raw_inbound = ib.raw_inbound or {}
        stream_settings = raw_inbound.get("streamSettings", {})
        network = stream_settings.get("network", ib.network or "")

        if network != "xhttp":
            continue

        total_checked += 1

        xhttp_settings = stream_settings.get("xhttpSettings", {})
        expected_path = xhttp_settings.get("path")
        expected_extra = xhttp_settings

        path_mismatch = host.path != expected_path
        extra_mismatch = host.x_http_extra_params != expected_extra

        if path_mismatch or extra_mismatch:
            mismatched_count += 1
            logger.info(f"Mismatch found on host '{host.remark}' ({host.uuid}):")
            if path_mismatch:
                logger.info(f"  Path: '{host.path}' -> expected '{expected_path}'")
            if extra_mismatch:
                logger.info(f"  x_http_extra_params: {host.x_http_extra_params} -> expected {expected_extra}")

            if apply:
                logger.info(f"  Applying updates to host '{host.remark}'...")
                try:
                    update_dto = UpdateHostRequestDto(
                        uuid=host.uuid,
                        path=expected_path,
                        x_http_extra_params=expected_extra
                    )
                    await sdk.hosts.update_host(update_dto)
                    logger.info("  ✓ Successfully updated.")
                    success_count += 1
                except Exception as e:
                    logger.error(f"  ✗ Failed to update host: {e}")
                    fail_count += 1
            else:
                logger.info(f"  [DRY-RUN] Would update host '{host.remark}' with expected settings.")

    # 4. Summary
    logger.info("\n=== Execution Summary ===")
    logger.info(f"Total xHTTP hosts checked: {total_checked}")
    logger.info(f"Mismatched hosts found:  {mismatched_count}")
    if apply:
        logger.info(f"Successfully updated:    {success_count}")
        logger.info(f"Failed to update:        {fail_count}")
    else:
        logger.info("Dry-run mode. No changes were applied.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync xHTTP settings from config profile inbounds to Remnawave hosts."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply changes to Remnawave (default: dry-run only)",
    )
    parser.add_argument(
        "--env",
        metavar="FILE",
        default=None,
        help="Path to a .env file to load (default: auto-detect)",
    )
    args = parser.parse_args()
    asyncio.run(sync_hosts(apply=args.apply, env_path=args.env))


if __name__ == "__main__":
    main()
