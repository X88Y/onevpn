#!/usr/bin/env python3
"""
Add a remote server as a node in Remnawave and deploy dependencies via SSH.

Usage:
    python add_remnawave_node.py <ip_address> [--ssh-key /path/to/id_rsa] [--user root] [--port 22]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

import paramiko
from remnawave import RemnawaveSDK
from remnawave.enums import Fingerprint, SecurityLayer
from remnawave.models import (
    CreateHostInboundData,
    CreateHostRequestDto,
    CreateNodeRequestDto,
    NodeConfigProfileRequestDto,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Constants matching existing configuration
DEFAULT_PROFILE_UUID = UUID("00000000-0000-0000-0000-000000000000")
REALITY_INBOUND_UUID = UUID("9902c9e2-a74c-4576-973d-4d2e7f23a093")
REALITY_INBOUND_TAG = "VLESS_TCP_REALITY"
REALITY_SNI = ""
REALITY_PORT = 443
HOST_TAG = "SPEED_SERVER"

COUNTRY_MAP = {
    "DE": ("🇩🇪", "Германия"),
    "GB": ("🇬🇧", "Британия"),
    "PL": ("🇵🇱", "Польша"),
    "HU": ("🇭🇺", "Венгрия"),
    "NL": ("🇳🇱", "Нидерланды"),
    "BY": ("🇧🇾", "Беларусь"),
    "FI": ("🇫🇮", "Финляндия"),
    "FR": ("🇫🇷", "Франция"),
    "SE": ("🇸🇪", "Швеция"),
    "CH": ("🇨🇭", "Швейцария"),
    "KZ": ("🇰🇿", "Казахстан"),
    "ES": ("🇪🇸", "Испания"),
    "IT": ("🇮🇹", "Италия"),
    "AT": ("🇦🇹", "Австрия"),
    "BG": ("🇧🇬", "Болгария"),
    "RO": ("🇷🇴", "Румыния"),
    "HR": ("🇭🇷", "Хорватия"),
    "ME": ("🇲🇪", "Черногория"),
    "MK": ("🇲🇰", "Северная Македония"),
    "MT": ("🇲🇹", "Мальта"),
    "NO": ("🇳🇴", "Норвегия"),
}

BASH_SCRIPT_TEMPLATE = r"""#!/bin/bash
set -e

# ── Detect OS ───────────────────────────────────────────────────────────────────
. /etc/os-release
OS_ID="${ID}"          # ubuntu / debian

# Robust detection of the OS codename (with fallbacks)
CODENAME="${VERSION_CODENAME:-${UBUNTU_CODENAME}}"
if [[ -z "$CODENAME" ]]; then
  if command -v lsb_release >/dev/null 2>&1; then
    CODENAME="$(lsb_release -cs)"
  elif [[ -n "$VERSION" ]]; then
    # Extract codename from VERSION field, e.g., "12 (bookworm)" -> "bookworm"
    CODENAME=$(echo "$VERSION" | sed -rn 's|.+\((.+)\).+|\1|p')
  fi
fi

if [[ "$OS_ID" != "ubuntu" && "$OS_ID" != "debian" ]]; then
  echo "Error: unsupported OS '$OS_ID'. Only Ubuntu and Debian are supported."
  exit 1
fi

if [[ -z "$CODENAME" ]]; then
  echo "Error: Could not automatically detect the OS codename (codename is empty)."
  exit 1
fi

echo "Detected: $PRETTY_NAME ($OS_ID / $CODENAME)"

# ── Clean Pre-existing Sources ──────────────────────────────────────────────────
# Remove potentially malformed docker repository files from previous failed runs.
# This prevents apt-get update from crashing at the start of the script.
rm -f /etc/apt/sources.list.d/docker.sources /etc/apt/sources.list.d/docker.list

# ── Install Docker ──────────────────────────────────────────────────────────────
apt-get update -qq
apt-get install -y -qq ca-certificates curl

install -m 0755 -d /etc/apt/keyrings
curl -fsSL "https://download.docker.com/linux/${OS_ID}/gpg" -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/${OS_ID}
Suites: ${CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# ── Deploy nginx → 200 OK ───────────────────────────────────────────────────────

cd /root/

cat > docker-compose.yml <<'EOF'

services:
  remnanode:
    container_name: remnanode
    hostname: remnanode
    image: remnawave/node:latest
    network_mode: host
    restart: always
    cap_add:
      - NET_ADMIN
    ulimits:
      nofile:
        soft: 1048576
        hard: 1048576
    environment:
      - NODE_PORT=2222
      - SECRET_KEY="{secret_key}"

EOF

docker compose up -d
"""


def _load_env(env_path: Optional[str] = None) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning("dotenv library not installed, relying on system env variables")
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
            logger.info(f"Loaded environment variables from {p}")
            return


def run_ssh_command(client: paramiko.SSHClient, command: str) -> int:
    """Executes a command via SSH and streams the output in real time."""
    logger.info(f"Executing command over SSH:\n{command[:120]}...")
    stdin, stdout, stderr = client.exec_command(command)

    # Stream stdout and stderr in real-time
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            data = stdout.channel.recv(4096).decode("utf-8", errors="ignore")
            print(data, end="", flush=True)
        if stdout.channel.recv_stderr_ready():
            data = stdout.channel.recv_stderr(4096).decode("utf-8", errors="ignore")
            print(data, end="", file=sys.stderr, flush=True)

    # Output any remaining data
    remaining_out = stdout.read().decode("utf-8", errors="ignore")
    if remaining_out:
        print(remaining_out, end="", flush=True)
    remaining_err = stderr.read().decode("utf-8", errors="ignore")
    if remaining_err:
        print(remaining_err, end="", file=sys.stderr, flush=True)

    exit_code = stdout.channel.recv_exit_status()
    return exit_code


async def add_node(
    ip_address: str,
    ssh_key_path: Optional[str],
    username: str,
    ssh_port: int,
    env_path: Optional[str],
) -> None:
    _load_env(env_path)

    remnawave_base = os.getenv("REMNAWAVE_BASE_URL") or os.getenv("REMNAWAVE_URL")
    remnawave_token = os.getenv("REMNAWAVE_API_TOKEN") or os.getenv("REMNAWAVE_TOKEN")

    if not remnawave_base or not remnawave_token:
        logger.error(
            "REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN must be set via environment or .env file."
        )
        sys.exit(1)

    # Pick random country
    country_code = random.choice(list(COUNTRY_MAP.keys()))
    flag, country_name = COUNTRY_MAP[country_code]
    logger.info(f"Randomly selected country: {flag} {country_name} ({country_code})")

    # Connect to Remnawave SDK
    sdk = RemnawaveSDK(base_url=remnawave_base, token=remnawave_token)

    # Step 1: Generate Node Key
    logger.info("Generating Remnawave node key...")
    try:
        keygen_res = await sdk.keygen.generate_key()
        secret_key = keygen_res.pub_key
        logger.info("Successfully generated node key.")
    except Exception as e:
        logger.error(f"Failed to generate node key: {e}")
        sys.exit(1)

    # Step 2: Register Node in Remnawave
    node_name = f"{ip_address}"[:30]
    logger.info(f"Registering node '{node_name}' on Remnawave...")

    node_dto = CreateNodeRequestDto(
        name=node_name,
        address=ip_address,
        port=2222,
        is_traffic_tracking_active=True,
        traffic_limit_bytes=0,
        notify_percent=80,
        traffic_reset_day=1,
        excluded_inbounds=[],
        country_code=country_code,
        consumption_multiplier=1.0,
        config_profile=NodeConfigProfileRequestDto(
            activeConfigProfileUuid=DEFAULT_PROFILE_UUID,
            activeInbounds=[REALITY_INBOUND_UUID],
        ),
    )

    try:
        node_res = await sdk.nodes.create_node(node_dto)
        node_uuid = node_res.uuid
        logger.info(f"Successfully registered node with UUID: {node_uuid}")
    except Exception as e:
        logger.error(f"Failed to register node in Remnawave: {e}")
        sys.exit(1)

    # Step 3: Connect via SSH and Run setup script
    logger.info(f"Connecting to {username}@{ip_address}:{ssh_port} via SSH...")
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        connect_kwargs = {
            "hostname": ip_address,
            "port": ssh_port,
            "username": username,
            "timeout": 30.0,
            "allow_agent": True,
            "look_for_keys": True,
        }
        if ssh_key_path:
            connect_kwargs["key_filename"] = ssh_key_path

        ssh_client.connect(**connect_kwargs)
        logger.info("Successfully connected to the remote server.")
    except Exception as e:
        logger.error(f"Failed to establish SSH connection to {ip_address}: {e}")
        logger.info("Rolling back Remnawave node registration...")
        try:
            await sdk.nodes.delete_node(str(node_uuid))
            logger.info("Rollback complete (node deleted).")
        except Exception as rb_err:
            logger.error(f"Failed to delete node during rollback: {rb_err}")
        sys.exit(1)

    try:
        # Prepare script content
        script_content = BASH_SCRIPT_TEMPLATE.replace("{secret_key}", secret_key)

        # Write setup script to /tmp/setup_remnanode.sh on remote server
        logger.info("Uploading installation script to remote server...")
        sftp = ssh_client.open_sftp()
        script_path = "/tmp/setup_remnanode.sh"
        with sftp.file(script_path, "w") as f:
            f.write(script_content)
        sftp.chmod(script_path, 0o755)
        sftp.close()
        logger.info("Upload complete.")

        # Execute setup script
        exit_code = run_ssh_command(ssh_client, f"bash {script_path}")
        if exit_code != 0:
            raise RuntimeError(f"Installation script failed with exit code {exit_code}")

        # Clean up script
        run_ssh_command(ssh_client, f"rm -f {script_path}")
        logger.info("Installation completed successfully.")

    except Exception as e:
        logger.error(f"Error during remote installation: {e}")
        logger.info("Rolling back Remnawave node registration...")
        try:
            await sdk.nodes.delete_node(str(node_uuid))
            logger.info("Rollback complete (node deleted).")
        except Exception as rb_err:
            logger.error(f"Failed to delete node during rollback: {rb_err}")
        sys.exit(1)
    finally:
        ssh_client.close()

    # Step 4: Create Host in Remnawave for the node
    host_remark = f"{flag} {country_name}"
    logger.info(f"Creating host '{host_remark}' in Remnawave panel...")

    inbound_data = CreateHostInboundData(
        config_profile_uuid=DEFAULT_PROFILE_UUID,
        config_profile_inbound_uuid=REALITY_INBOUND_UUID,
    )

    host_dto = CreateHostRequestDto(
        inbound=inbound_data,
        remark=host_remark,
        address=ip_address,
        port=REALITY_PORT,
        sni=REALITY_SNI,
        host="",
        fingerprint=Fingerprint.CHROME,
        tag=HOST_TAG,
        nodes=[node_uuid],
        security_layer=SecurityLayer.DEFAULT,
        is_hidden=False,
        override_sni_from_address=False,
        keep_blank_sni=False,
    )

    try:
        await sdk.hosts.create_host(host_dto)
        logger.info("Successfully created Remnawave host mapping.")
    except Exception as e:
        logger.error(f"Failed to create Host in Remnawave: {e}")
        logger.warning(
            "The node was set up successfully and remains registered, but you will need to map the host manually."
        )
        sys.exit(1)

    logger.info(f"\n🎉 Node successfully deployed and registered!")
    logger.info(f"Node UUID: {node_uuid}")
    logger.info(f"Node Name: {node_name}")
    logger.info(f"Host:      {host_remark} ({ip_address}:{REALITY_PORT})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision a server, register it in Remnawave, and run deployment scripts."
    )
    parser.add_argument("ip_address", help="The target server IP address.")
    parser.add_argument(
        "--ssh-key",
        metavar="PATH",
        default=None,
        help="Path to the local private key file (e.g. ~/.ssh/id_rsa).",
    )
    parser.add_argument(
        "--user",
        default="root",
        help="SSH username for connecting to the target server (default: root).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=22,
        help="SSH port of the target server (default: 22).",
    )
    parser.add_argument(
        "--env",
        metavar="FILE",
        default=None,
        help="Path to the .env configuration file (default: auto-detect).",
    )

    args = parser.parse_args()

    asyncio.run(
        add_node(
            ip_address=args.ip_address,
            ssh_key_path=args.ssh_key,
            username=args.user,
            ssh_port=args.port,
            env_path=args.env,
        )
    )


if __name__ == "__main__":
    main()
