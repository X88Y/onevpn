import asyncio
import json
import logging
import sys
import os

# Add the backend directory to sys.path so we can import from 'server_manager' package
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from server_manager.xui.client import XuiClient, XuiServer
from server_manager.xui.inbound import build_default_vless_reality_payload, random_inbound_port

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_create_inbound():
    server = XuiServer(
        server_id="test-manual",
        panel_url="https://2.27.44.230:59054/b4dbc9ad6bba8926",
        username="mvm-f1714781",
        password="VZQBAy4aixJWHHZGemF47F8o"
    )

    print(f"--- Connecting to {server.panel_url} ---")
    
    async with XuiClient(server, verify=False) as xui:
        try:
            print("Logging in...")
            await xui.login()
            print("Login successful!")

            print("Fetching new X25519 cert...")
            cert = await xui.new_x25519_cert()
            if not cert:
                print("Failed to get new X25519 cert")
                return
            
            print(f"Cert obtained. Public Key: {cert['publicKey']}")

            inbound_port = random_inbound_port()
            print(f"Creating inbound on port {inbound_port}...")
            payload = build_default_vless_reality_payload(
                port=inbound_port,
                private_key=cert["privateKey"],
                public_key=cert["publicKey"],
                remark="mvm-test-manual"
            )
            
            result = await xui.add_inbound(payload)
            print("Inbound created successfully!")
            print(json.dumps(result, indent=2))

            inbound_id = result.get("id")
            if inbound_id:
                print(f"\n--- Adding test client to inbound {inbound_id} ---")
                test_uuid = "95804797-25e4-490b-936b-733306637e1a"
                test_email = "test-manual-user@mvm.vpn"
                await xui.add_client(
                    inbound_id=inbound_id,
                    client_uuid=test_uuid,
                    email=test_email,
                    sub_id="testsub123"
                )
                print(f"Client {test_email} added successfully!")
            else:
                print("Could not find inbound ID in result, skipping client creation.")

            inbounds = await xui.list_inbounds()
            print(f"Current inbounds: {len(inbounds)}")
            for ib in inbounds:
                print(f" - ID: {ib.get('id')}, Remark: {ib.get('remark')}, Port: {ib.get('port')}")

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_create_inbound())
