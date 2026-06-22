import asyncio
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore  # type: ignore[import-not-found,import-untyped]

from mvm_bot.datetime_utils import as_utc_datetime


async def extend_doc_subscription(
    db: firestore.Client,
    doc_ref: firestore.DocumentReference,
    days: int,
) -> None:
    transaction = db.transaction()

    @firestore.transactional
    def run(transaction: firestore.Transaction) -> None:
        snapshot = doc_ref.get(transaction=transaction)
        data = snapshot.to_dict() or {}
        now = datetime.now(timezone.utc)
        current_end = as_utc_datetime(data.get("subscriptionEndsAt"))
        base = current_end if current_end and current_end > now else now
        transaction.set(
            doc_ref,
            {"subscriptionEndsAt": base + timedelta(days=days), "updatedAt": firestore.SERVER_TIMESTAMP},
            merge=True,
        )

    await asyncio.to_thread(run, transaction)
