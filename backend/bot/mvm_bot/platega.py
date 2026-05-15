"""Platega payment gateway — create transaction checkout links."""

from __future__ import annotations

import json
from typing import Any, NamedTuple, Optional, Union

from aiohttp import ClientError, ClientSession


class PlategaCheckout(NamedTuple):
    """Platega redirect URL and ``payload`` passed to the API (webhook correlation)."""

    url: str
    payload: str


TRANSACTION_API_URL = "https://app.platega.io/v2/transaction/process"


async def create_transaction(
    *,
    merchant_id: str,
    secret: str,
    amount: float,
    currency: str,
    description: str,
    payload: str,
    return_url: Optional[str] = None,
    failed_url: Optional[str] = None,
) -> dict[str, Any]:
    body_data: dict[str, Any] = {
        "paymentDetails": {"amount": amount, "currency": currency},
        "description": description,
        "payload": payload,
    }
    if return_url:
        body_data["return"] = return_url
    if failed_url:
        body_data["failedUrl"] = failed_url

    body = json.dumps(body_data)
    headers = {
        "Content-Type": "application/json",
        "X-MerchantId": merchant_id,
        "X-Secret": secret,
    }
    try:
        async with ClientSession() as session:
            async with session.post(
                TRANSACTION_API_URL,
                data=body,
                headers=headers,
                timeout=30,
            ) as resp:
                raw = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"Platega HTTP {resp.status}: {raw}")
    except ClientError as e:
        raise RuntimeError(f"Platega request failed: {e}") from e

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("Platega returned non-object JSON")
    return data


async def transaction_checkout_url(
    *,
    merchant_id: str,
    secret: str,
    provider: str,
    user_id: Union[int, str],
    plan_key: str,
    amount: float,
    currency: str,
    description: str,
    return_url: Optional[str] = None,
    failed_url: Optional[str] = None,
) -> PlategaCheckout:
    """Create a Platega transaction and return the checkout URL plus payload.

    The ``payload`` field encodes ``{provider}:{user_id}:{plan_key}`` so the
    Firebase webhook can identify the buyer and extend their subscription.
    """
    platega_payload = f"{provider}:{user_id}:{plan_key}"
    data = await create_transaction(
        merchant_id=merchant_id,
        secret=secret,
        amount=amount,
        currency=currency,
        description=description,
        payload=platega_payload,
        return_url=return_url,
        failed_url=failed_url,
    )
    url = data.get("url")
    if not isinstance(url, str) or not url:
        raise RuntimeError(f"Platega transaction missing url: {data!r}")
    return PlategaCheckout(url=url, payload=platega_payload)
