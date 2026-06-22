from datetime import datetime, timedelta, timezone

from firebase_admin import firestore  # type: ignore[import-not-found,import-untyped]

from mvm_bot.datetime_utils import as_utc_datetime


def extend_subscription_days(
    *,
    db: firestore.Client,
    doc_ref: firestore.DocumentReference,
    days: int,
) -> dict:
    transaction = db.transaction()

    @firestore.transactional
    def run(transaction: firestore.Transaction) -> dict:
        snapshot = doc_ref.get(transaction=transaction)
        data = snapshot.to_dict() or {}
        now = datetime.now(timezone.utc)
        current_end = as_utc_datetime(data.get("subscriptionEndsAt"))
        base = current_end if current_end and current_end > now else now
        payload = {
            "subscriptionEndsAt": base + timedelta(days=days),
            "updatedAt": firestore.SERVER_TIMESTAMP,
        }
        transaction.set(doc_ref, payload, merge=True)
        return {**data, **payload}

    return run(transaction)


def extend_subscription_with_tier(
    *,
    db: firestore.Client,
    doc_ref: firestore.DocumentReference,
    days: int,
    tier: str,
) -> dict:
    transaction = db.transaction()

    @firestore.transactional
    def run(transaction: firestore.Transaction) -> dict:
        snapshot = doc_ref.get(transaction=transaction)
        data = snapshot.to_dict() or {}
        now = datetime.now(timezone.utc)
        current_end = as_utc_datetime(data.get("subscriptionEndsAt"))
        current_tier = data.get("subscriptionTier")

        if tier == "premium" and current_tier == "standart":
            base = now
        else:
            base = current_end if current_end and current_end > now else now

        payload = {
            "subscriptionEndsAt": base + timedelta(days=days),
            "subscriptionTier": tier,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        }
        transaction.set(doc_ref, payload, merge=True)
        return {**data, **payload}

    return run(transaction)
