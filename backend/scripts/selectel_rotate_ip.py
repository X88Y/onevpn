"""Rotate Selectel public ports until an IP falls in the CIDR whitelist.

Calls POST /public-network/v1/public_ports to allocate a new public IP,
checks it against cidrwhitelist.txt, and deletes non-whitelisted IPs before
retrying.

Usage:
    python selectel_rotate_ip.py
"""

import sys
import time
from pathlib import Path

import httpx

from rotate_ip import is_ip_in_whitelist, load_cidr_whitelist

SELECTEL_AUTH_TOKEN = (
    "gAAAAABqM9r29dUgjH8Ml1DQt5K-0Y_bNAOqZXrDXnpKPEoiFtLBmXobaaqK4xzaFE7jj0HbVZOU4EIfhlz36-4sPyp3pyRfkrcTe3Tq6dE-KaA9OQO5MW_drUUzfQ_jFo73wJTFxTdNg9FGpVa4dnzLTCVGih4eOnY51UNFzVlciyuXGqbPOKA"
)
BASE_URL = "https://ru-2.cloud.api.selcloud.ru/public-network/v1/public_ports"


def _headers(token: str) -> dict[str, str]:
    return {
        "x-auth-token": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def create_public_port(headers: dict[str, str]) -> tuple[str, str]:
    resp = httpx.post(BASE_URL, headers=headers, json={}, timeout=30.0)
    if resp.status_code != 201:
        print(f"Error creating public port (status {resp.status_code}): {resp.text}")
        sys.exit(1)

    port = resp.json().get("port") or {}
    ip_str = port.get("ip_address")
    port_id = port.get("id")
    if not ip_str or not port_id:
        print(f"Error: unexpected create response: {resp.text}")
        sys.exit(1)
    return ip_str, port_id


def delete_public_port(headers: dict[str, str], port_id: str, ip_str: str) -> None:
    resp = httpx.delete(f"{BASE_URL}/{port_id}", headers=headers, timeout=30.0)
    if resp.status_code not in (200, 204):
        print(f"Error deleting public port {ip_str} (status {resp.status_code}): {resp.text}")
        sys.exit(1)


def rotate_ip(token: str, networks: list) -> None:
    headers = _headers(token)

    resp = httpx.get(BASE_URL, headers=headers, timeout=30.0)
    if resp.status_code != 200:
        print(f"Error: auth check failed (status {resp.status_code}): {resp.text}")
        sys.exit(1)
    print("Connected successfully to Selectel public-network API.")

    attempt = 0
    while True:
        attempt += 1
        print(f"Attempt {attempt}: creating public port...")

        try:
            ip_str, port_id = create_public_port(headers)
        except Exception as e:
            print(f"Error during public port creation: {e}")
            sys.exit(1)

        print(f"Attempt {attempt}: created IP {ip_str} (ID: {port_id})")

        if is_ip_in_whitelist(ip_str, networks):
            print(f"Attempt {attempt}: success! IP {ip_str} is in the whitelist. Keeping it.")
            break

        print(f"Attempt {attempt}: IP {ip_str} is NOT in the whitelist. Deleting...")
        try:
            delete_public_port(headers, port_id, ip_str)
            print(f"Attempt {attempt}: IP {ip_str} deleted successfully.")
        except Exception as e:
            print(f"Error during public port deletion: {e}")
            sys.exit(1)

        time.sleep(1.0)


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    whitelist_path = script_dir / "cidrwhitelist.txt"
    if not whitelist_path.exists():
        print(f"Error: whitelist file not found at {whitelist_path}")
        sys.exit(1)

    networks = load_cidr_whitelist(whitelist_path)
    token = SELECTEL_AUTH_TOKEN.strip()
    if not token:
        print("Error: SELECTEL_AUTH_TOKEN is empty")
        sys.exit(1)

    print("Starting Selectel IP rotation...")
    rotate_ip(token, networks)
    print("Rotation completed successfully.")


if __name__ == "__main__":
    main()
