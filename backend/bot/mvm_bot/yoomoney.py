"""YooMoney Quickpay payment — generate redirect links for the payment form.

YooMoney does not require a server-side API call to create a payment.
The bot constructs a URL that sends the user directly to the YooMoney
payment page (https://yoomoney.ru/quickpay/confirm) with the required
form parameters.

Reference: https://yoomoney.ru/docs/payment-buttons/using-api/forms
"""

from __future__ import annotations

import time
import httpx
import logging
from typing import NamedTuple, Optional, Union

logger = logging.getLogger(__name__)

QUICKPAY_URL = "https://yoomoney.ru/quickpay/confirm"

# Payment types
PAYMENT_TYPE_CARD = "AC"    # from any bank card
PAYMENT_TYPE_SBP = "SB"     # via СБП (Система Быстрых Платежей)


class YooMoneyCheckout(NamedTuple):
    """Result of building a YooMoney/YooKassa checkout link."""

    url: str
    label: str


def build_label(provider: str, user_id: Union[int, str], plan_key: str) -> str:
    """Build the correlation label embedded in the payment link.

    Format: ``mvm_{provider}_{user_id}_{plan_key}_{nonce}``
    Matches the ORDER_ID_RE pattern already used by the FreeKassa webhook.
    The label is passed back verbatim in the YooMoney HTTP notification.
    """
    nonce = int(time.time() * 1000)
    return f"mvm_{provider}_{user_id}_{plan_key}_{nonce}"


def map_payment_type(payment_type: str) -> str:
    if payment_type == PAYMENT_TYPE_SBP:
        return "sbp"
    else:
        return "bank_card"


async def checkout_url(
    *,
    receiver: str,
    provider: str,
    user_id: Union[int, str],
    plan_key: str,
    amount: float,
    payment_type: str = PAYMENT_TYPE_CARD,
    success_url: Optional[str] = None,
) -> YooMoneyCheckout:
    """Create a YooKassa payment via API and return the confirmation URL and label.

    Parameters
    ----------
    receiver:
        The YooKassa Shop ID (e.g. ``"560918144706"``).
    provider:
        Bot channel — ``"tg"`` or ``"vk"``.
    user_id:
        Telegram / VK user ID.
    plan_key:
        Subscription plan key (e.g. ``"plan_30"``).
    amount:
        Amount in RUB.
    payment_type:
        ``"PC"`` for wallet, ``"AC"`` for card, or ``"SB"`` for SBP.
    success_url:
        Optional redirect URL after successful payment.
    """
    label = build_label(provider, user_id, plan_key)
    mapped_type = map_payment_type(payment_type)

    from mvm_bot.config import yoomoney_secret, yoomoney_recurring_enabled
    secret = yoomoney_secret()
    if not secret:
        raise ValueError("Yoomoney/Yookassa secret is not configured.")

    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "payment_method_data": {
            "type": mapped_type
        },
        "confirmation": {
            "type": "redirect",
            "return_url": success_url or "https://t.me"
        },
        "capture": True,
        "save_payment_method": yoomoney_recurring_enabled(),
        "description": f"MVMVpn подписка — {plan_key}",
        "metadata": {
            "label": label
        }
    }

    headers = {
        "Idempotence-Key": label,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.yookassa.ru/v3/payments",
            json=payload,
            headers=headers,
            auth=(receiver, secret),
            timeout=15.0
        )
        if response.status_code not in (200, 201):
            logger.error(f"YooKassa payment creation failed: {response.status_code} {response.text}")
            raise RuntimeError(f"YooKassa API returned {response.status_code}")

        data = response.json()
        confirmation = data.get("confirmation") or {}
        confirmation_url = confirmation.get("confirmation_url")
        if not confirmation_url:
            raise RuntimeError("YooKassa response is missing confirmation_url")

        return YooMoneyCheckout(url=confirmation_url, label=label)
