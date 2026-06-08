#!/usr/bin/env python3
"""One-time script to delete the `remnawaveSubscriptionUrl` field from all users."""

import os
import sys
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore


def _find_service_account() -> Path | None:
    """Look for a Firebase service-account JSON in the backend root."""
    backend_root = Path(__file__).resolve().parent.parent
    for pattern in ("*-firebase-adminsdk-*.json", "serviceAccount.json", "firebase-adminsdk.json"):
        matches = list(backend_root.glob(pattern))
        if matches:
            return matches[0]
    return None


def init_firestore() -> firestore.Client:
    if not firebase_admin._apps:
        sa = _find_service_account()
        if sa is not None:
            firebase_admin.initialize_app(credentials.Certificate(str(sa)))
        else:
            firebase_admin.initialize_app()
    return firestore.client()


def main() -> None:
    db = init_firestore()
    users_col = db.collection("users")

    # Stream all user documents and batch-update those that contain the field.
    batch = db.batch()
    batch_count = 0
    total = 0
    BATCH_SIZE = 500  # Firestore batch limit is 500

    print("Scanning users collection for `remnawaveSubscriptionUrl` ...")
    for doc in users_col.stream():
        data = doc.to_dict() or {}
        if "remnawaveSubscriptionUrl" in data:
            batch.update(doc.reference, {"remnawaveSubscriptionUrl": firestore.DELETE_FIELD})
            batch_count += 1
            total += 1

            if batch_count >= BATCH_SIZE:
                batch.commit()
                print(f"  Committed {batch_count} deletions...")
                batch = db.batch()
                batch_count = 0

    if batch_count:
        batch.commit()
        print(f"  Committed {batch_count} deletions...")

    print(f"Done. Removed `remnawaveSubscriptionUrl` from {total} user document(s).")


if __name__ == "__main__":
    main()
