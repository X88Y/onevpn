"""FreeKassa payment gateway — create orders via API v1."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, NamedTuple, Optional, Union

from aiohttp import ClientError, ClientSession


class FreeKassaCheckout(NamedTuple):
    """Result of creating a FreeKassa order: redirect URL and merchant order id."""

    url: str
    payment_id: str


API_BASE = "https://api.fk.life/v1"

# Payment system IDs (i parameter)
PAYMENT_SBP = 44       # СБП (QR code)
PAYMENT_CARD_RU = 36   # Банковские карты РФ
PAYMENT_SBERPAY = 43   # СберПэй


def _build_signature(data: dict[str, Any], api_key: str) -> str:
    """Compute HMAC-SHA256 signature.

    Sort fields by key alphabetically, join values with ``|``, then
    compute HMAC-SHA256 using the API key as the secret.
    """
    sorted_values = [str(data[k]) for k in sorted(data.keys())]
    message = "|".join(sorted_values)
    return hmac.new(api_key.encode(), message.encode(), hashlib.sha256).hexdigest()


def _normalize_amount(amount: float) -> Union[int, float]:
    """Convert amount to a stable JSON number used for signing.

    FreeKassa recalculates signatures from parsed request values. If we sign
    ``479.0`` but the gateway stringifies that value as ``479``, signatures
    diverge. This normalizes integer-like prices to ``int`` and keeps non-zero
    fractional amounts with up to 2 decimals.
    """
    try:
        dec = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return amount
    if dec == dec.to_integral_value():
        return int(dec)
    return float(dec)


def _make_nonce() -> int:
    """Return a monotonically-increasing nonce (ms since epoch + 3h buffer)."""
    return int((time.time() + 10800) * 1000)


async def create_order(
    *,
    shop_id: int,
    api_key: str,
    payment_id: str,
    payment_system: int,
    email: str,
    ip: str,
    amount: float,
    currency: str = "RUB",
    success_url: Optional[str] = None,
    failure_url: Optional[str] = None,
    notification_url: Optional[str] = None,
) -> dict[str, Any]:
    """Create a FreeKassa order via API and return the response dict.

    The checkout URL is at ``response['location']``.

    Raises ``RuntimeError`` on HTTP errors or non-success API responses.
    """
    nonce = _make_nonce()
    normalized_amount = _normalize_amount(amount)
    data: dict[str, Any] = {
        "shopId": shop_id,
        "nonce": nonce,
        "paymentId": payment_id,
        "i": payment_system,
        "email": email,
        "ip": ip,
        "amount": normalized_amount,
        "currency": currency,
    }
    if success_url:
        data["success_url"] = success_url
    if failure_url:
        data["failure_url"] = failure_url
    if notification_url:
        data["notification_url"] = notification_url
    # sort data by key alphabetically
    data = dict(sorted(data.items()))
    data["signature"] = _build_signature(data, api_key)
    body = json.dumps(data)
    try:
        async with ClientSession() as session:
            async with session.post(
                f"{API_BASE}/orders/create",
                data=body,
                headers={"Content-Type": "text/plain"},
                timeout=30,
            ) as resp:
                raw = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"FreeKassa HTTP {resp.status}: {raw}")
    except ClientError as e:
        raise RuntimeError(f"FreeKassa request failed: {e}") from e

    result = json.loads(raw)
    if not isinstance(result, dict):
        raise RuntimeError("FreeKassa returned non-object JSON")
    if result.get("type") != "success":
        raise RuntimeError(f"FreeKassa API error: {result}")
    return result


async def checkout_url(
    *,
    shop_id: int,
    api_key: str,
    provider: str,
    user_id: Union[int, str],
    plan_key: str,
    payment_system: int,
    email: str,
    ip: str,
    amount: float,
    currency: str = "RUB",
    success_url: Optional[str] = None,
    failure_url: Optional[str] = None,
    notification_url: Optional[str] = None,
) -> FreeKassaCheckout:
    """Create a FreeKassa order and return the checkout URL plus ``paymentId``.

    The ``paymentId`` follows the ``mvm:{provider}:{user_id}:{plan_key}:{nonce}``
    format so the Firebase webhook can identify the buyer and extend their
    subscription.
    """
    nonce = _make_nonce()
    payment_id = f"mvm_{provider}_{user_id}_{plan_key}_{nonce}"
    result = await create_order(
        shop_id=shop_id,
        api_key=api_key,
        payment_id=payment_id,
        payment_system=payment_system,
        email=email,
        ip=ip,
        amount=amount,
        currency=currency,
        success_url=success_url,
        failure_url=failure_url,
        notification_url=notification_url,
    )
    location = result.get("location")
    if not isinstance(location, str) or not location:
        raise RuntimeError(f"FreeKassa order missing location: {result!r}")
    return FreeKassaCheckout(url=location, payment_id=payment_id)
