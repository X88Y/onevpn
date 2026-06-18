import httpx
import sys
from rotate_ip import timeweb_tokens

def check_balance_for_token(token, token_idx):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    base_url = "https://timeweb.cloud"
    
    try:
        info_resp = httpx.get(f"{base_url}/api/v2/accounts/info", headers=headers, timeout=30.0)
        email = None
        if info_resp.status_code == 200:
            email = info_resp.json().get("account", {}).get("email")
        else:
            print(f"Token {token_idx}: Account info failed (status {info_resp.status_code}): {info_resp.text}")

        resp = httpx.get(f"{base_url}/api/v1/account/finances", headers=headers, timeout=30.0)
        if resp.status_code == 200:
            data = resp.json()
            finances = data.get("finances", {})
            balance = finances.get("balance")
            currency = finances.get("currency", "RUB")
            hourly_cost = finances.get("hourly_cost")

            print(f"Token {token_idx}: Connected successfully.")
            if email:
                print(f"  Email: {email}")
            print(f"  Balance: {balance} {currency}")
            print(f"  Hourly Cost: {hourly_cost} {currency}")
        else:
            print(f"Token {token_idx}: Failed (status code {resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"Token {token_idx}: Connection failed: {e}")

def main():
    tokens = [t.strip() for t in timeweb_tokens.strip().split('\n') if t.strip()]
    if not tokens:
        print("Error: No tokens found in rotate_ip.py")
        sys.exit(1)
        
    print(f"Found {len(tokens)} tokens. Checking finances...")
    for idx, token in enumerate(tokens, 1):
        print(f"\n--- Checking Token {idx}/{len(tokens)} ---")
        check_balance_for_token(token, idx)
        
    print("\nFinances check completed.")

if __name__ == '__main__':
    main()
