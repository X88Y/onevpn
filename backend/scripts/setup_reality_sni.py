"""Create GoDaddy A records for Reality hosts and set custom SNI on each host.

For every VLESS_TCP_REALITY host on Default-Profile nodes:
1. Create/update GoDaddy A record: {node}-rl.sub.{domain} -> node IP
2. Update Remnawave host address and SNI to that domain

Usage:
    python setup_reality_sni.py                  # dry-run
    python setup_reality_sni.py --apply          # apply DNS + host updates
    python setup_reality_sni.py --env /path/.env
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

import httpx
from dotenv import load_dotenv
from remnawave import RemnawaveSDK
from remnawave.models import UpdateHostRequestDto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

REALITY_INBOUND_UUID = UUID("9902c9e2-a74c-4576-973d-4d2e7f23a093")
DNS_LABEL_SUFFIX = "rl"


def _load_env(env_path: Optional[str] = None) -> None:
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


def make_dns_safe(name: str) -> str:
    safe_name = name.lower()
    safe_name = re.sub(r"[^a-z0-9\-]", "-", safe_name)
    safe_name = re.sub(r"-+", "-", safe_name)
    return safe_name.strip("-")


def reality_sni_domain(node_name: str, godaddy_domain: str) -> tuple[str, str]:
    """Return (record_name, full_fqdn) for a node's Reality SNI."""
    dns_safe = make_dns_safe(node_name)
    record_name = f"{dns_safe}-{DNS_LABEL_SUFFIX}.sub"
    fqdn = f"{record_name}.{godaddy_domain}"
    return record_name, fqdn


class GoDaddyClient:
    def __init__(self, key: str, secret: str, base_url: str = "https://api.godaddy.com"):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"sso-key {key}:{secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_or_update_a_record(
        self, domain: str, name: str, ip: str, ttl: int = 600
    ) -> None:
        url = f"{self.base_url}/v1/domains/{domain}/records/A/{name}"
        payload = [{"data": ip, "ttl": ttl}]
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.put(url, headers=self.headers, json=payload)
            if resp.status_code not in (200, 201):
                logger.error(
                    f"Failed to set GoDaddy DNS record: {resp.status_code} {resp.text}"
                )
                resp.raise_for_status()
        logger.info(f"GoDaddy A record: {name}.{domain} -> {ip}")


async def run_setup(*, apply: bool, env_path: Optional[str] = None) -> None:
    _load_env(env_path)

    remnawave_base = os.getenv("REMNAWAVE_BASE_URL") or os.getenv("REMNAWAVE_URL")
    remnawave_token = os.getenv("REMNAWAVE_API_TOKEN") or os.getenv("REMNAWAVE_TOKEN")
    godaddy_key = os.getenv("GODADDY_API_KEY")
    godaddy_secret = os.getenv("GODADDY_API_SECRET")
    godaddy_domain = os.getenv("GODADDY_DOMAIN", "duck69.xyz")

    if not remnawave_base or not remnawave_token:
        logger.error("REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN must be set")
        sys.exit(1)
    if not godaddy_key or not godaddy_secret:
        logger.error("GODADDY_API_KEY and GODADDY_API_SECRET must be set")
        sys.exit(1)

    sdk = RemnawaveSDK(base_url=remnawave_base, token=remnawave_token)
    gd_client = GoDaddyClient(key=godaddy_key, secret=godaddy_secret)

    nodes = await sdk.nodes.get_all_nodes()
    hosts = await sdk.hosts.get_all_hosts()
    node_by_uuid = {n.uuid: n for n in nodes}

    reality_hosts = [
        h
        for h in hosts
        if h.inbound and h.inbound.config_profile_inbound_uuid == REALITY_INBOUND_UUID
    ]
    logger.info(f"Found {len(reality_hosts)} VLESS_TCP_REALITY hosts.")

    dns_updated = 0
    sni_updated = 0
    skipped = 0

    for host in reality_hosts:
        node = next(
            (node_by_uuid[nid] for nid in host.nodes if nid in node_by_uuid),
            None,
        )
        if not node:
            logger.warning(f"  No node found for host '{host.remark}', skipping")
            skipped += 1
            continue

        record_name, fqdn = reality_sni_domain(node.name, godaddy_domain)
        ip = node.address

        if host.sni == fqdn and host.address == fqdn:
            logger.info(
                f"[-] {host.remark}: address and SNI already '{fqdn}', skipping"
            )
            skipped += 1
            continue

        logger.info(f"\n{host.remark} (node={node.name}, ip={ip})")
        logger.info(f"  DNS: {fqdn} -> {ip}")
        logger.info(f"  Host address: {host.address!r} -> {fqdn!r}")
        logger.info(f"  Host SNI: {host.sni!r} -> {fqdn!r}")

        if apply:
            try:
                await gd_client.create_or_update_a_record(
                    domain=godaddy_domain,
                    name=record_name,
                    ip=ip,
                )
                dns_updated += 1
            except Exception as e:
                logger.error(f"  GoDaddy failed: {e}")
                continue

            try:
                update_dto = UpdateHostRequestDto(
                    uuid=host.uuid,
                    address=fqdn,
                    sni=fqdn,
                    override_sni_from_address=False,
                    keep_blank_sni=False,
                )
                await sdk.hosts.update_host(update_dto)
                logger.info(f"  Host address and SNI updated to '{fqdn}'")
                sni_updated += 1
            except Exception as e:
                logger.error(f"  Remnawave update failed: {e}")
        else:
            logger.info("  [DRY-RUN] Would create DNS record and update host address/SNI")
            dns_updated += 1
            sni_updated += 1

    logger.info("\nExecution summary:")
    logger.info(f"  Reality hosts:  {len(reality_hosts)}")
    if apply:
        logger.info(f"  DNS updated:    {dns_updated}")
        logger.info(f"  SNI updated:    {sni_updated}")
    else:
        logger.info(f"  Would update DNS: {dns_updated}")
        logger.info(f"  Would update SNI: {sni_updated}")
    logger.info(f"  Skipped:        {skipped}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create GoDaddy A records and set custom address/SNI on Reality hosts."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply DNS and Remnawave host updates",
    )
    parser.add_argument(
        "--env",
        metavar="FILE",
        default=None,
        help="Path to a .env file to load",
    )
    args = parser.parse_args()
    asyncio.run(run_setup(apply=args.apply, env_path=args.env))


if __name__ == "__main__":
    main()
