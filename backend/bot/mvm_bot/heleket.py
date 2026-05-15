"""Heleket payment invoice creation (crypto / fiat checkout)."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any, NamedTuple, Optional

from aiohttp import ClientError, ClientSession


class HeleketInvoice(NamedTuple):
    """Created invoice: payment page URL and our ``order_id`` sent to Heleket."""

    url: str
    order_id: str


API_BASE = "https://api.heleket.com/v1/payment"

_REQ_HEADERS_COMMON = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}


def _amount_str(price_amount: float) -> str:
    d = Decimal(str(price_amount))
    s = format(d, "f").rstrip("0").rstrip(".")
    return s if s else "0"


def _request_sign(body_json: str, api_key: str) -> str:
    b64 = base64.b64encode(body_json.encode("utf-8")).decode("ascii")
    return hashlib.md5((b64 + api_key).encode("utf-8")).hexdigest()


def _payment_invoice_payload(data: dict[str, Any]) -> dict[str, Any]:
    """API may return a flat invoice object or wrap it in ``{\"state\", \"result\"}``."""
    result = data.get("result")
    if isinstance(result, dict):
        url = result.get("url")
        if isinstance(url, str) and url:
            return result
    return data


async def create_invoice(
    *,
    merchant_uuid: str,
    api_key: str,
    ipn_callback_url: str,
    price_amount: float,
    price_currency: str,
    order_id: str,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "amount": _amount_str(price_amount),
        "currency": price_currency.upper(),
        "order_id": order_id,
        "url_callback": ipn_callback_url,
    }
    if success_url:
        payload["url_success"] = success_url
    if cancel_url:
        payload["url_return"] = cancel_url

    body_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    # Match PHP json_encode default (escaped slashes) used by Heleket signing.
    body_json = body_json.replace("/", r"\/")
    sign = _request_sign(body_json, api_key)
    headers = {
        **_REQ_HEADERS_COMMON,
        "Content-Type": "application/json",
        "merchant": merchant_uuid,
        "sign": sign,
    }
    try:
        async with ClientSession() as session:
            async with session.post(
                API_BASE,
                data=body_json.encode("utf-8"),
                headers=headers,
                timeout=30,
            ) as resp:
                raw = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"Heleket HTTP {resp.status}: {raw}")
    except ClientError as e:
        raise RuntimeError(f"Heleket request failed: {e}") from e

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("Heleket returned non-object JSON")
    state = data.get("state")
    if state not in (None, 0, "0"):
        raise RuntimeError(f"Heleket API error state={state!r}: {data!r}")
    return data


def build_order_id(provider: str, payer_user_id: int, plan_key: str) -> str:
    short = uuid.uuid4().hex[:12]
    return f"mvm-{provider}-{payer_user_id}-{plan_key}-{short}"


async def invoice_checkout_url(
    *,
    merchant_uuid: str,
    api_key: str,
    ipn_callback_url: str,
    payer_user_id: int,
    payer_provider: str = "tg",
    plan_key: str,
    price_amount: float,
    price_currency: str = "usd",
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
) -> HeleketInvoice:
    order_id = build_order_id(payer_provider, payer_user_id, plan_key)
    data = await create_invoice(
        merchant_uuid=merchant_uuid,
        api_key=api_key,
        ipn_callback_url=ipn_callback_url,
        price_amount=price_amount,
        price_currency=price_currency,
        order_id=order_id,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    invoice = _payment_invoice_payload(data)
    url = invoice.get("url")
    if not isinstance(url, str) or not url:
        raise RuntimeError(f"Heleket invoice missing url: {data!r}")
    return HeleketInvoice(url=url, order_id=order_id)
