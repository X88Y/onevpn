from typing import Any

from firebase_admin import firestore  # type: ignore[import-not-found,import-untyped]

from mvm_bot.firebase_client import init_firebase


def record_payment_checkout_click(
    *,
    service: str,
    provider: str,
    external_user_id: str,
    plan_key: str,
    amount: float,
    currency: str,
    pay_url: str,
    channel: str,
    correlation_id: str = None,
    payment_method: str = None,
    payment_system: int = None,
) -> None:
    """Append one Firestore document per generated external pay link (user tap)."""
    payload: dict[str, Any] = {
        "service": service,
        "provider": provider,
        "externalUserId": external_user_id,
        "planKey": plan_key,
        "amount": amount,
        "currency": currency,
        "payUrl": pay_url,
        "channel": channel,
        "createdAt": firestore.SERVER_TIMESTAMP,
    }
    if correlation_id is not None:
        payload["correlationId"] = correlation_id
    if payment_method is not None:
        payload["paymentMethod"] = payment_method
    if payment_system is not None:
        payload["paymentSystem"] = payment_system

    db = init_firebase()
    db.collection("payment_checkout_clicks").add(payload)
