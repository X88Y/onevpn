#!/usr/bin/env python3
"""Create Remnawave panel users for all Firebase users that are missing one.

For users that already have ``remnawaveUuid`` / ``remnawaveShortUuid`` stored in
Firestore but whose panel entry no longer exists, the user is recreated on the
panel using exactly the same UUID and shortUuid so that subscription URLs stay
unchanged.

For users with no Remnawave fields at all, the panel assigns new IDs which are
then written back to Firestore.

Usage:
    python scripts/create_missing_remnawave_users.py [--dry-run] [--env PATH]
"""

import sys
import os
import asyncio
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("create_missing_remnawave_users")

# ---------------------------------------------------------------------------
# Path resolution — mirror pattern from sync_users.py
# ---------------------------------------------------------------------------
script_dir = Path(__file__).resolve().parent
backend_dir = script_dir.parent if script_dir.name == "scripts" else script_dir
bot_dir = backend_dir / "bot"
if not bot_dir.is_dir():
    if (backend_dir / "mvm_bot").is_dir():
        bot_dir = backend_dir
    else:
        logger.error("Cannot find bot/ directory. Run this from backend/.")
        sys.exit(1)

sys.path.insert(0, str(bot_dir))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", default=None, help="Path to .env file.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without touching Firebase or Remnawave.",
    )
    p.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Remnawave helpers
# ---------------------------------------------------------------------------

async def get_rw_user_by_uuid(sdk: Any, uuid_str: str) -> Optional[Any]:
    try:
        return await sdk.users.get_user_by_uuid(uuid=uuid_str)
    except Exception as exc:
        if "404" in str(exc) or "not found" in str(exc).lower():
            return None
        raise


async def get_rw_user_by_username(sdk: Any, username: str) -> Optional[Any]:
    try:
        return await sdk.users.get_user_by_username(username)
    except Exception as exc:
        if "404" in str(exc) or "not found" in str(exc).lower():
            return None
        raise


async def create_rw_user(
    sdk: Any,
    username: str,
    expire_at: datetime,
    status_str: str,
    *,
    uuid_str: Optional[str] = None,
    short_uuid_str: Optional[str] = None,
    telegram_id: Optional[int] = None,
    squad_uuid_str: Optional[str] = None,
    description: Optional[str] = None,
) -> Any:
    from remnawave.enums import TrafficLimitStrategy, UserStatus
    from remnawave.models import CreateUserRequestDto
    from uuid import UUID

    squads = [UUID(squad_uuid_str)] if squad_uuid_str else None

    body = CreateUserRequestDto(
        username=username,
        expire_at=expire_at,
        status=UserStatus(status_str),
        traffic_limit_strategy=TrafficLimitStrategy("NO_RESET"),
        telegram_id=telegram_id,
        active_internal_squads=squads,
        description=description,
        uuid=UUID(uuid_str) if uuid_str else None,
        short_uuid=short_uuid_str or None,
    )
    return await sdk.users.create_user(body)


# Error codes that warrant a retry with fewer constraints
_CONFLICT_CODES = {
    "a018",  # CREATE_USER_ERROR — generic panel-side failure
    "a019",  # USER_USERNAME_ALREADY_EXISTS
    "a020",  # USER_SHORT_UUID_ALREADY_EXISTS
    "a021",  # USER_SUBSCRIPTION_UUID_ALREADY_EXISTS
}


async def _create_with_fallback(
    sdk: Any,
    *,
    username: str,
    expire_at: datetime,
    status_str: str,
    uuid_str: Optional[str],
    short_uuid_str: Optional[str],
    telegram_id: Optional[int],
    squad_uuid_str: Optional[str],
    description: Optional[str],
    user_uid: str,
) -> Optional[Any]:
    """Try to create a Remnawave user, falling back gracefully on conflicts.

    Attempt order:
      1. With preserved uuid + short_uuid  (keeps subscription URL intact)
      2. With preserved uuid only          (new short_uuid assigned by panel)
      3. With no uuid/short_uuid           (fully fresh user)

    After each failure the panel is re-queried by username in case A019 fired
    (race condition / partial previous run).  Returns the created/found user
    object, or None on unrecoverable error.
    """
    attempts = [
        {"uuid_str": uuid_str,  "short_uuid_str": short_uuid_str},
        {"uuid_str": uuid_str,  "short_uuid_str": None},
        {"uuid_str": None,      "short_uuid_str": None},
    ]
    # Drop duplicate attempts when uuid_str/short_uuid_str are both None from start
    seen: list = []
    unique_attempts = []
    for a in attempts:
        key = (a["uuid_str"], a["short_uuid_str"])
        if key not in seen:
            seen.append(key)
            unique_attempts.append(a)

    last_exc: Optional[Exception] = None
    for attempt in unique_attempts:
        try:
            resp = await create_rw_user(
                sdk,
                username=username,
                expire_at=expire_at,
                status_str=status_str,
                uuid_str=attempt["uuid_str"],
                short_uuid_str=attempt["short_uuid_str"],
                telegram_id=telegram_id,
                squad_uuid_str=squad_uuid_str,
                description=description,
            )
            if attempt["uuid_str"] != uuid_str or attempt["short_uuid_str"] != short_uuid_str:
                logger.warning(
                    "Created panel user '%s' for %s with different IDs "
                    "(uuid=%s shortUuid=%s). Subscription URL will change.",
                    username, user_uid,
                    attempt["uuid_str"] or "<panel-assigned>",
                    attempt["short_uuid_str"] or "<panel-assigned>",
                )
            return resp

        except Exception as exc:
            exc_str = str(exc).lower()
            is_conflict = any(code in exc_str for code in _CONFLICT_CODES)

            # A019 (username conflict): the user already exists — fetch and reuse it
            if "a019" in exc_str or "username already exists" in exc_str:
                existing = await get_rw_user_by_username(sdk, username)
                if existing is not None:
                    logger.warning(
                        "Create conflict (A019) for '%s'; using existing panel user uuid=%s.",
                        username, existing.uuid,
                    )
                    return existing

            if is_conflict and attempt != unique_attempts[-1]:
                logger.warning(
                    "Create attempt failed for '%s' (uuid=%s shortUuid=%s): %s "
                    "— retrying with fewer ID constraints.",
                    username,
                    attempt["uuid_str"] or "<none>",
                    attempt["short_uuid_str"] or "<none>",
                    exc,
                )
                last_exc = exc
                continue

            # Non-conflict error or last attempt exhausted
            logger.error(
                "Failed to create panel user for Firebase user %s: %s",
                user_uid, exc,
            )
            return None

    logger.error(
        "All create attempts exhausted for Firebase user %s (last error: %s).",
        user_uid, last_exc,
    )
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    args = parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Resolve .env
    if args.env:
        env_path = Path(args.env)
    elif (bot_dir / ".env").exists():
        env_path = bot_dir / ".env"
    elif (backend_dir / "server_manager" / ".env").exists():
        env_path = backend_dir / "server_manager" / ".env"
    else:
        env_path = Path(".env")

    if env_path.exists():
        load_dotenv(env_path)
        logger.info("Loaded environment from %s", env_path)
    else:
        logger.warning("No .env file found at %s — relying on system env.", env_path)

    # Late imports so env vars are available
    try:
        from firebase_admin import firestore
        from mvm_bot.firebase_client import init_firebase
        from mvm_bot.datetime_utils import as_utc_datetime
        from mvm_bot.config import remnawave_internal_squad_uuid
        from mvm_bot.user_service.remnawave import build_user_description
        from remnawave import RemnawaveSDK
    except ImportError as exc:
        logger.error("Import error: %s  — are you in the correct venv?", exc)
        sys.exit(1)

    base_url = os.getenv("REMNAWAVE_BASE_URL")
    api_token = os.getenv("REMNAWAVE_API_TOKEN")
    if not base_url or not api_token:
        logger.error("REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN must be set.")
        sys.exit(1)

    logger.info("Initializing Firebase and Remnawave SDK…")
    db = init_firebase()
    sdk = RemnawaveSDK(base_url=base_url, token=api_token)

    logger.info("Fetching all Firebase users…")
    users_ref = db.collection("users")
    fb_snaps = await asyncio.to_thread(lambda: list(users_ref.stream()))
    logger.info("Loaded %d users from Firestore.", len(fb_snaps))

    created_count = 0
    skipped_count = 0
    error_count = 0

    for snap in fb_snaps:
        user_uid: str = snap.id
        user_data: Dict[str, Any] = snap.to_dict() or {}

        existing_rw_uuid: Optional[str] = user_data.get("remnawaveUuid") or None
        existing_rw_short: Optional[str] = user_data.get("remnawaveShortUuid") or None

        # Standard username format (strips hyphens to stay within 36-char limit)
        username_std = f"mvm-{user_uid.replace('-', '')}"

        # ------------------------------------------------------------------
        # Step 1: check whether a panel user already exists
        # ------------------------------------------------------------------
        panel_user = None

        if existing_rw_uuid:
            # Firestore claims a UUID — verify the panel entry exists
            panel_user = await get_rw_user_by_uuid(sdk, existing_rw_uuid)
            if panel_user:
                logger.debug(
                    "User %s already has a panel entry (uuid=%s). Skipping.",
                    user_uid, existing_rw_uuid,
                )
                skipped_count += 1
                continue

            # UUID not found — try the username before giving up
            panel_user = await get_rw_user_by_username(sdk, username_std)
            if panel_user:
                # Panel user exists under username but UUID differs; update Firestore
                new_uuid = str(panel_user.uuid)
                new_short = str(panel_user.short_uuid)
                new_sub_url = str(panel_user.subscription_url)
                if not args.dry_run:
                    await asyncio.to_thread(
                        lambda: users_ref.document(user_uid).update(
                            {
                                "remnawaveUuid": new_uuid,
                                "remnawaveShortUuid": new_short,
                                "remnawaveSubscriptionUrl": new_sub_url,
                                "updatedAt": firestore.SERVER_TIMESTAMP,
                            }
                        )
                    )
                    logger.info(
                        "Fixed stale UUID for %s: Firestore had %s, panel has %s.",
                        user_uid, existing_rw_uuid, new_uuid,
                    )
                else:
                    logger.info(
                        "[Dry Run] Would fix stale UUID for %s: %s → %s.",
                        user_uid, existing_rw_uuid, new_uuid,
                    )
                skipped_count += 1
                continue
        else:
            # No UUID in Firestore at all — check by username
            panel_user = await get_rw_user_by_username(sdk, username_std)
            if panel_user:
                # Panel user exists but Firestore fields are missing; backfill them
                new_uuid = str(panel_user.uuid)
                new_short = str(panel_user.short_uuid)
                new_sub_url = str(panel_user.subscription_url)
                if not args.dry_run:
                    await asyncio.to_thread(
                        lambda: users_ref.document(user_uid).update(
                            {
                                "remnawaveUuid": new_uuid,
                                "remnawaveShortUuid": new_short,
                                "remnawaveSubscriptionUrl": new_sub_url,
                                "updatedAt": firestore.SERVER_TIMESTAMP,
                            }
                        )
                    )
                    logger.info(
                        "Backfilled missing Firestore fields for %s (uuid=%s).",
                        user_uid, new_uuid,
                    )
                else:
                    logger.info(
                        "[Dry Run] Would backfill Firestore for %s (uuid=%s).",
                        user_uid, new_uuid,
                    )
                skipped_count += 1
                continue

        # ------------------------------------------------------------------
        # Step 2: no panel user found — create one
        # ------------------------------------------------------------------
        ends_at = as_utc_datetime(user_data.get("subscriptionEndsAt"))
        now = datetime.now(timezone.utc)
        is_active = bool(ends_at and ends_at > now)
        target_status = "ACTIVE" if is_active else "DISABLED"
        # Remnawave rejects expire_at in the past on creation; use a safe minimum
        rw_expire_at = ends_at if is_active else now + timedelta(minutes=10)

        # Telegram ID
        tg_id: Optional[int] = None
        ext_tg = user_data.get("externalTg")
        if isinstance(ext_tg, str):
            raw = ext_tg[3:] if ext_tg.startswith("tg:") else ext_tg
            try:
                tg_id = int(raw)
            except ValueError:
                pass
        elif isinstance(ext_tg, int):
            tg_id = ext_tg

        target_description = await build_user_description(user_uid, user_data)

        if args.dry_run:
            action = (
                f"with preserved UUID={existing_rw_uuid}, shortUuid={existing_rw_short}"
                if existing_rw_uuid
                else "with a new Remnawave-assigned UUID"
            )
            logger.info(
                "[Dry Run] Would create panel user '%s' for Firebase user %s %s "
                "(status=%s, expiry=%s, tg_id=%s).",
                username_std, user_uid, action, target_status, rw_expire_at, tg_id,
            )
            created_count += 1
            continue

        resp = await _create_with_fallback(
            sdk,
            username=username_std,
            expire_at=rw_expire_at,
            status_str=target_status,
            uuid_str=existing_rw_uuid,
            short_uuid_str=existing_rw_short,
            telegram_id=tg_id,
            squad_uuid_str=remnawave_internal_squad_uuid(),
            description=target_description,
            user_uid=user_uid,
        )
        if resp is None:
            error_count += 1
            continue

        new_uuid = str(resp.uuid)
        new_short = str(resp.short_uuid)
        new_sub_url = str(resp.subscription_url)

        await asyncio.to_thread(
            lambda: users_ref.document(user_uid).update(
                {
                    "remnawaveUuid": new_uuid,
                    "remnawaveShortUuid": new_short,
                    "remnawaveSubscriptionUrl": new_sub_url,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                }
            )
        )

        if existing_rw_uuid:
            logger.info(
                "Recreated panel user '%s' for %s with preserved uuid=%s.",
                username_std, user_uid, new_uuid,
            )
        else:
            logger.info(
                "Created panel user '%s' for %s with new uuid=%s.",
                username_std, user_uid, new_uuid,
            )
        created_count += 1

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    logger.info("Done.")
    logger.info("  Firebase users processed : %d", len(fb_snaps))
    logger.info("  Panel users created      : %d", created_count)
    logger.info("  Already existed (skipped): %d", skipped_count)
    logger.info("  Errors                   : %d", error_count)


if __name__ == "__main__":
    asyncio.run(main())
