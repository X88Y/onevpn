from pathlib import Path
from typing import List, TypedDict

BOT_ADMIN_DIR = Path(__file__).resolve().parent
VPN_KEYS_COLLECTION = "vpn_keys"


class VpnPlan(TypedDict):
    id: str
    label: str
    amount: float
    currency: str
    days: int


VPN_PLANS: List[VpnPlan] = [
    {"id": "1m", "label": "1 month", "amount": 300.0, "currency": "RUB", "days": 30},
    {"id": "3m", "label": "3 months", "amount": 800.0, "currency": "RUB", "days": 90},
    {"id": "6m", "label": "6 months", "amount": 1500.0, "currency": "RUB", "days": 180},
]
