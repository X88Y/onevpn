"""Auto-create Timeweb CDNs and Remnawave hosts for TW_CDN tagged nodes.

1. Fetch all nodes with tag 'TW_CDN' from Remnawave.
2. For each node, verify if a CDN resource already exists in Timeweb.
3. If not, create a CDN resource with name 'mvm-cdn-{node_name}' pointing to the node IP.
4. Turn off cache on the Timeweb CDN resource.
5. Create or update a hidden host in Remnawave pointing to the new CDN domain name.
   Name: 🇪🇺💎Моб Инет обход {COUNTRY_CODE}|TW
   Tag: BYPASS_WL
   Hidden: True

Usage:
    python time_web.py                  # dry-run, prints actions
    python time_web.py --apply          # actually applies changes to Timeweb and Remnawave
    python time_web.py --env /path/.env # load a specific .env file
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional
from uuid import UUID

import httpx
from remnawave import RemnawaveSDK
from remnawave.models import CreateHostRequestDto, CreateHostInboundData, UpdateHostRequestDto
from remnawave.enums import SecurityLayer, Fingerprint

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


# ---------------------------------------------------------------------------
# TimeWeb Client
# ---------------------------------------------------------------------------
class TimeWebClient:
    def __init__(self, token: str, base_url: str = "https://timeweb.cloud"):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        }

    async def get_default_project_id(self) -> int:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/projects",
                headers=self.headers
            )
            if resp.status_code == 200:
                data = resp.json()
                projects = data if isinstance(data, list) else data.get("projects") or []
                if not projects:
                    raise RuntimeError("No projects found in Timeweb account.")
                for p in projects:
                    if p.get("is_default") or p.get("is_main"):
                        return p.get("id")
                return projects[0].get("id")
            else:
                logger.error(f"Failed to list projects: {resp.status_code} {resp.text}")
                resp.raise_for_status()

    async def get_cdn_preset_id(self) -> int:
        endpoints = [
            "/api/v1/presets/cdn",
            "/api/v1/cdn/presets",
            "/api/v1/cdn/http-resources/presets",
        ]
        async with httpx.AsyncClient(timeout=60.0) as client:
            for ep in endpoints:
                try:
                    resp = await client.get(f"{self.base_url}{ep}", headers=self.headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        presets = data if isinstance(data, list) else data.get("presets") or data.get("cdn_presets") or []
                        if presets:
                            for p in presets:
                                if p.get("id") == 3807 or "default" in str(p.get("description", "")).lower():
                                    return p.get("id")
                            if isinstance(presets[0], dict) and "id" in presets[0]:
                                return presets[0]["id"]
                            elif isinstance(presets[0], (int, str)):
                                return int(presets[0])
                except Exception as e:
                    logger.debug(f"Failed to query endpoint {ep}: {e}")
        logger.warning("Could not auto-detect CDN preset ID. Using fallback preset ID 3807.")
        return 3807

    async def list_cdn_resources(self) -> List[dict]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/cdn/http-resources",
                headers=self.headers
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                return data.get("http_resources") or []
            else:
                logger.error(f"Failed to list CDN resources: {resp.status_code} {resp.text}")
                resp.raise_for_status()

    async def create_cdn_resource(self, name: str, host_ip: str, project_id: int, preset_id: int) -> dict:
        payload = {
            "name": name,
            "description": "",
            "project_id": project_id,
            "preset_id": preset_id,
            "server": {
                "host": host_ip,
                "port": 443
            },
            "use_https": False
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/cdn/http-resources",
                headers=self.headers,
                json=payload
            )
            if resp.status_code in (200, 201):
                return resp.json()
            else:
                logger.error(f"Failed to create CDN resource: {resp.status_code} {resp.text}")
                resp.raise_for_status()

    async def disable_cache(self, resource_id: int) -> None:
        payload = {
            "config": {
                "cache": {
                    "cdn": None,
                    "browser": None,
                    "always_online": None,
                    "query_args": {
                        "mode": "all"
                    }
                }
            }
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.patch(
                f"{self.base_url}/api/v1/cdn/http-resources/{resource_id}",
                headers=self.headers,
                json=payload
            )
            if resp.status_code not in (200, 204):
                logger.error(f"Failed to disable CDN cache: {resp.status_code} {resp.text}")
                resp.raise_for_status()


def extract_cdn_info(data: dict):
    """Extract resource ID and CDN CNAME domain from TimeWeb API response."""
    resource = data.get("http_resource") or data
    if isinstance(resource, list) and len(resource) > 0:
        resource = resource[0]
        
    resource_id = resource.get("id")
    cname = resource.get("cname") or resource.get("domain") or resource.get("cdn_domain")
    
    if not cname:
        # Search all keys for something ending with twcstorage.ru or cdn
        for v in resource.values():
            if isinstance(v, str) and ("twcstorage.ru" in v or "cdn" in v):
                cname = v
                break
    return resource_id, cname


def make_dns_safe(name: str) -> str:
    """Convert node name to a safe subdomain label."""
    import re
    # Lowercase, replace non-alphanumeric (excluding hyphen) with hyphen
    safe_name = name.lower()
    safe_name = re.sub(r'[^a-z0-9\-]', '-', safe_name)
    safe_name = re.sub(r'-+', '-', safe_name)
    return safe_name.strip('-')


class GoDaddyClient:
    def __init__(self, key: str, secret: str, base_url: str = "https://api.godaddy.com"):
        self.key = key
        self.secret = secret
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"sso-key {key}:{secret}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def create_or_update_a_record(self, domain: str, name: str, ip: str, ttl: int = 600) -> None:
        url = f"{self.base_url}/v1/domains/{domain}/records/A/{name}"
        payload = [
            {
                "data": ip,
                "ttl": ttl
            }
        ]
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.put(url, headers=self.headers, json=payload)
            if resp.status_code in (200, 201):
                logger.info(f"Successfully set GoDaddy A record: {name}.{domain} -> {ip}")
            elif resp.status_code == 200:
                logger.info(f"Successfully set GoDaddy A record: {name}.{domain} -> {ip}")
            else:
                logger.error(f"Failed to set GoDaddy DNS record: {resp.status_code} {resp.text}")
                resp.raise_for_status()


# ---------------------------------------------------------------------------
# Core Logic
# ---------------------------------------------------------------------------
class CallbackLogHandler(logging.Handler):
    def __init__(self, callback: Callable[[str], None]):
        super().__init__()
        self.callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.callback(msg)
        except Exception:
            self.handleError(record)


# ---------------------------------------------------------------------------
# Core Logic
# ---------------------------------------------------------------------------
async def run_sync(*, token: str, apply: bool, env_path: Optional[str] = None, log_callback: Optional[Callable[[str], None]] = None) -> None:
    handler = None
    if log_callback:
        handler = CallbackLogHandler(log_callback)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

    try:
        _load_env(env_path)

        # Handle if token was passed as token=...
        if token.startswith("token="):
            token = token.split("token=", 1)[1]

        # Generate a single 2-character suffix once on start for all resources created in this run
        import random
        import string
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=2))
        logger.info(f"Generated suffix for this execution run: {suffix}")

        # Remnawave Config
        remnawave_base = os.getenv("REMNAWAVE_BASE_URL") or os.getenv("REMNAWAVE_URL")
        remnawave_token = os.getenv("REMNAWAVE_API_TOKEN") or os.getenv("REMNAWAVE_TOKEN")

        if not remnawave_base or not remnawave_token:
            logger.error(
                "REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN must be set "
                "(via environment or .env file)"
            )
            sys.exit(1)

        host_tag = os.getenv("HOST_TAG", "BYPASS_WL")

        # GoDaddy Config
        godaddy_key = os.getenv("GODADDY_API_KEY", "h2JrEBpTXqkB_5UqmTT45FCngsCqvDRisJf")
        godaddy_secret = os.getenv("GODADDY_API_SECRET", "XrGHB6E55JfRLjhA5wTJn2")
        godaddy_domain = os.getenv("GODADDY_DOMAIN", "duck69.xyz")

        # Initialize clients
        sdk = RemnawaveSDK(base_url=remnawave_base, token=remnawave_token)
        tw_client = TimeWebClient(token=token)
        gd_client = GoDaddyClient(key=godaddy_key, secret=godaddy_secret)

        # Auto-detect Project ID if not configured
        project_id_env = os.getenv("TIMEWEB_PROJECT_ID")
        if project_id_env:
            timeweb_project_id = int(project_id_env)
        else:
            logger.info("Auto-detecting Timeweb Project ID...")
            try:
                timeweb_project_id = await tw_client.get_default_project_id()
                logger.info(f"Auto-detected Project ID: {timeweb_project_id}")
            except Exception as e:
                logger.warning(f"Could not auto-detect Project ID: {e}. Using fallback 2573125.")
                timeweb_project_id = 2573125

        # Auto-detect Preset ID if not configured
        preset_id_env = os.getenv("TIMEWEB_PRESET_ID")
        if preset_id_env:
            timeweb_preset_id = int(preset_id_env)
        else:
            logger.info("Auto-detecting Timeweb CDN Preset ID...")
            try:
                timeweb_preset_id = await tw_client.get_cdn_preset_id()
                logger.info(f"Auto-detected Preset ID: {timeweb_preset_id}")
            except Exception as e:
                logger.warning(f"Could not auto-detect Preset ID: {e}. Using fallback 3807.")
                timeweb_preset_id = 3807

        # Fetch nodes from Remnawave
        logger.info("Fetching nodes from Remnawave...")
        try:
            nodes = await sdk.nodes.get_all_nodes()
        except Exception as e:
            logger.error(f"Failed to fetch nodes from Remnawave: {e}")
            sys.exit(1)

        # Filter for TW_CDN tagged nodes
        tw_cdn_nodes = [node for node in nodes if "TW_CDN" in node.tags]
        logger.info(f"Found {len(tw_cdn_nodes)} nodes with 'TW_CDN' tag out of {len(nodes)} total nodes.")

        if not tw_cdn_nodes:
            logger.info("No nodes with 'TW_CDN' tag. Exiting.")
            return

        # Fetch existing hosts from Remnawave
        logger.info("Fetching existing hosts from Remnawave...")
        try:
            existing_hosts = await sdk.hosts.get_all_hosts()
        except Exception as e:
            logger.error(f"Failed to fetch hosts from Remnawave: {e}")
            sys.exit(1)

        # Fetch existing CDN resources from TimeWeb
        tw_resources = []
        logger.info("Fetching existing CDN resources from TimeWeb...")
        try:
            tw_resources = await tw_client.list_cdn_resources()
            logger.info(f"Found {len(tw_resources)} existing CDN resources on TimeWeb.")
        except Exception as e:
            logger.error(f"Failed to list TimeWeb CDN resources: {e}")
            if apply:
                sys.exit(1)

        for node in tw_cdn_nodes:
            logger.info(f"\nProcessing node: {node.name} (IP: {node.address}, Country: {node.country_code})")
            
            # Expected CDN resource name and Host remark
            cdn_name = f"mvm-cdn-{node.name}-{suffix.lower()}"
            remark = f"🇪🇺LTE Только в MVM приложении {node.country_code.upper()}|TW|{suffix}"

            # Create GoDaddy DNS record
            dns_safe_name = make_dns_safe(node.name)
            subdomain_record_name = f"{dns_safe_name}-{suffix.lower()}.sub"
            origin_domain = f"{subdomain_record_name}.{godaddy_domain}"

            if apply:
                logger.info(f"  Ensuring GoDaddy A record: {origin_domain} -> {node.address}...")
                try:
                    await gd_client.create_or_update_a_record(
                        domain=godaddy_domain,
                        name=subdomain_record_name,
                        ip=node.address
                    )
                except Exception as e:
                    logger.error(f"  Failed to create/update GoDaddy A record: {e}")
                    raise e
            else:
                logger.info(f"  [DRY-RUN] Would ensure GoDaddy A record: {origin_domain} -> {node.address}")

            # Check if CDN resource already exists
            existing_res = next((r for r in tw_resources if r.get("name") == cdn_name), None)
            
            resource_id = None
            cdn_domain = None

            if existing_res:
                resource_id, cdn_domain = extract_cdn_info(existing_res)
                logger.info(f"  CDN resource already exists in TimeWeb: ID={resource_id}, Domain={cdn_domain}")
                # Ensure cache is disabled even if it exists
                if apply:
                    logger.info(f"  Ensuring CDN cache is disabled for resource {resource_id}...")
                    await tw_client.disable_cache(resource_id)
            else:
                if apply:
                    logger.info(f"  Creating new CDN resource '{cdn_name}' in TimeWeb for origin '{origin_domain}'...")
                    res_data = await tw_client.create_cdn_resource(
                        name=cdn_name,
                        host_ip=origin_domain,
                        project_id=timeweb_project_id,
                        preset_id=timeweb_preset_id
                    )
                    resource_id, cdn_domain = extract_cdn_info(res_data)
                    logger.info(f"  CDN created successfully: ID={resource_id}, Domain={cdn_domain}")
                    
                    logger.info(f"  Disabling cache on CDN resource {resource_id}...")
                    await tw_client.disable_cache(resource_id)
                else:
                    logger.info(f"  [DRY-RUN] Would create CDN resource '{cdn_name}' in TimeWeb for origin '{origin_domain}'")
                    logger.info(f"  [DRY-RUN] Would disable cache on the new CDN resource")
                    resource_id = 99999
                    cdn_domain = f"placeholder-{node.name}.cdn.twcstorage.ru"

            if not cdn_domain:
                logger.error(f"  Could not determine CDN domain for node {node.name}. Skipping host creation.")
                continue

            # Check if Remnawave Host already exists
            existing_host = next((h for h in existing_hosts if h.remark == remark), None)

            if existing_host:
                logger.info(f"  Remnawave host already exists: remark='{remark}', UUID={existing_host.uuid}, Address={existing_host.address}")
                if existing_host.address != cdn_domain:
                    if apply:
                        logger.info(f"  Updating Remnawave host address to '{cdn_domain}'...")
                        update_dto = UpdateHostRequestDto(
                            uuid=existing_host.uuid,
                            address=cdn_domain
                        )
                        await sdk.hosts.update_host(update_dto)
                        logger.info("  Host updated successfully.")
                    else:
                        logger.info(f"  [DRY-RUN] Would update Remnawave host address from '{existing_host.address}' to '{cdn_domain}'")
                else:
                    logger.info("  Remnawave host address is already correct. No update needed.")
            else:
                # Pick active config profile and inbound details
                cp = node.config_profile
                cp_uuid = cp.active_config_profile_uuid
                
                # Find the best inbound (prefer AISUDJIAUSHD tag, then security='none')
                inbound = None
                if cp.active_inbounds:
                    inbound = next((ib for ib in cp.active_inbounds if ib.tag == "AISUDJIAUSHD"), None)
                    if not inbound:
                        inbound = next((ib for ib in cp.active_inbounds if ib.security == "none"), None)
                    if not inbound:
                        inbound = cp.active_inbounds[0]

                if not inbound:
                    logger.error(f"  No active inbound found on node {node.name}. Cannot create Remnawave host.")
                    continue

                # Extract WS/xHTTP stream config
                raw_inbound = inbound.raw_inbound or {}
                stream_settings = raw_inbound.get("streamSettings", {})
                network = stream_settings.get("network", "xhttp")
                
                path = None
                x_http_extra_params = None

                if network == "xhttp":
                    xhttp_settings = stream_settings.get("xhttpSettings", {})
                    path = xhttp_settings.get("path")
                    x_http_extra_params = xhttp_settings
                elif network == "ws":
                    ws_settings = stream_settings.get("wsSettings", {})
                    path = ws_settings.get("path")
                else:
                    path = "/"

                if apply:
                    logger.info(f"  Creating hidden Remnawave host: remark='{remark}', target_cdn='{cdn_domain}'...")
                    
                    inbound_data = CreateHostInboundData(
                        config_profile_uuid=cp_uuid,
                        config_profile_inbound_uuid=inbound.uuid
                    )
                    
                    req_dto = CreateHostRequestDto(
                        inbound=inbound_data,
                        remark=remark,
                        address=cdn_domain,
                        port=443,
                        path=path,
                        sni="",
                        host="",
                        fingerprint=Fingerprint.CHROME,
                        security_layer=SecurityLayer.TLS,
                        is_hidden=False, # Hide by default!
                        override_sni_from_address=True,
                        keep_blank_sni=False,
                        allow_insecure=False,
                        shuffle_host=False,
                        mihomo_x25519=False,
                        nodes=[node.uuid],
                        x_http_extra_params=x_http_extra_params,
                        tag=host_tag
                    )
                    
                    await sdk.hosts.create_host(req_dto)
                    logger.info("  Host created successfully.")
                else:
                    logger.info(f"  [DRY-RUN] Would create hidden Remnawave host:")
                    logger.info(f"    Remark: '{remark}'")
                    logger.info(f"    Address: '{cdn_domain}'")
                    logger.info(f"    Inbound: '{inbound.tag}' (UUID: {inbound.uuid})")
                    logger.info(f"    Path: '{path}'")
                    logger.info(f"    Network: '{network}'")

        if not apply:
            logger.info("\nDry-run complete. Run with --apply to apply changes to TimeWeb and Remnawave.")
    finally:
        if handler:
            logger.removeHandler(handler)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-create Timeweb CDNs and Remnawave hosts for TW_CDN tagged nodes."
    )
    parser.add_argument(
        "token",
        help="Timeweb API access token",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply changes to Timeweb and Remnawave",
    )
    parser.add_argument(
        "--env",
        metavar="FILE",
        default=None,
        help="Path to a .env file to load (default: auto-detect)",
    )
    args = parser.parse_args()
    
    asyncio.run(run_sync(token=args.token, apply=args.apply, env_path=args.env))


if __name__ == "__main__":
    main()