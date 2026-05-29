#!/usr/bin/env python3
"""Sync users and subscription links between Firebase Firestore and Remnawave panel.

Firebase acts as the source of truth for user details.
"""

import sys
from pathlib import Path
import os
import argparse
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("sync_users")

# Discover directories
script_dir = Path(__file__).resolve().parent
backend_dir = script_dir.parent if script_dir.name == "scripts" else script_dir
bot_dir = backend_dir / "bot"
if not bot_dir.is_dir():
    if (backend_dir / "mvm_bot").is_dir():
        bot_dir = backend_dir
    else:
        logger.error("Cannot find bot/ directory. Ensure you run this from backend/")
        sys.exit(1)

# Add bot directory to python path
sys.path.insert(0, str(bot_dir))

def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync users between Firebase Firestore and Remnawave Panel."
    )
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="Path to .env file to load (defaults to bot/.env or server_manager/.env)."
    )
    parser.add_argument(
        "--cleanup-action",
        choices=["none", "disable", "delete"],
        default="none",
        help="Action to perform on orphaned Remnawave users (default: none)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without modifying Firebase or Remnawave."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose debug logs."
    )
    return parser.parse_args()

def parse_rw_datetime(val: Any) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    try:
        s = str(val)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def normalize_sub_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path
        path_parts = [p for p in path.split('/') if p]
        if not path_parts:
            return url
        short_uuid = path_parts[-1]
        return f"{scheme}://{netloc}/{short_uuid}"
    except Exception:
        return url

async def list_all_remnawave_users(sdk) -> List[Any]:
    offset = 0
    size = 100
    all_users = []
    while True:
        try:
            resp = await sdk.users.get_all_users(start=offset, size=size)
            users = resp.users
            if not users:
                break
            all_users.extend(users)
            if len(users) < size or len(all_users) >= resp.total:
                break
            offset += size
        except Exception as exc:
            logger.error(f"Failed to fetch Remnawave users at offset {offset}: {exc}")
            raise
    return all_users

async def update_rw_user(
    sdk,
    uuid_str: str,
    current_status_str: str,
    target_status_str: str,
    expire_at: Optional[datetime] = None,
    telegram_id: Optional[int] = None,
    description: Optional[str] = None,
):
    """Update a Remnawave user's metadata and status.

    Status changes (ACTIVE <-> DISABLED) are applied via the dedicated
    action endpoints (/actions/enable, /actions/disable) because Remnawave
    auto-manages EXPIRED/LIMITED and rejects them in PATCH requests.
    Metadata-only updates (description, telegram_id, expire_at) go via PATCH.
    """
    from remnawave.models import UpdateUserRequestDto
    from uuid import UUID

    # Build metadata PATCH body (no status field)
    body = UpdateUserRequestDto(uuid=UUID(uuid_str))
    has_metadata = False
    # Only set expire_at for ACTIVE users; past dates make Remnawave set EXPIRED
    if expire_at is not None and target_status_str == "ACTIVE":
        body.expire_at = expire_at
        has_metadata = True
    if telegram_id is not None:
        body.telegram_id = telegram_id
        has_metadata = True
    if description is not None:
        body.description = description
        has_metadata = True

    if has_metadata:
        await sdk.users.update_user(body)

    # Apply status change via dedicated action endpoints
    current = current_status_str.upper()
    target = target_status_str.upper()
    if target == "ACTIVE" and current != "ACTIVE":
        try:
            await sdk.users.enable_user(uuid=uuid_str)
        except Exception as exc:
            exc_str = str(exc).lower()
            # A030: Remnawave auto-activates the user when a future expire_at is
            # PATCH'd on an EXPIRED user, so enable_user then fails. Treat as success.
            if "already enabled" in exc_str or "a030" in exc_str:
                logger.debug("enable_user ignored (already active) uuid=%s", uuid_str)
            else:
                raise
    elif target == "DISABLED" and current == "ACTIVE":
        try:
            await sdk.users.disable_user(uuid=uuid_str)
        except Exception as exc:
            exc_str = str(exc).lower()
            if "already disabled" in exc_str:
                logger.debug("disable_user ignored (already disabled) uuid=%s", uuid_str)
            else:
                raise

async def create_rw_user(
    sdk,
    username: str,
    expire_at: datetime,
    status_str: str,
    telegram_id: Optional[int] = None,
    squad_uuid_str: Optional[str] = None,
    description: Optional[str] = None
):
    from remnawave.enums import TrafficLimitStrategy, UserStatus
    from remnawave.models import CreateUserRequestDto
    from uuid import UUID
    
    squads = None
    if squad_uuid_str:
        squads = [UUID(squad_uuid_str)]
        
    body = CreateUserRequestDto(
        username=username,
        expire_at=expire_at,
        status=UserStatus(status_str),
        traffic_limit_strategy=TrafficLimitStrategy("NO_RESET"),
        telegram_id=telegram_id,
        active_internal_squads=squads,
        description=description
    )
    return await sdk.users.create_user(body)

async def disable_rw_user(sdk, uuid_str: str):
    await sdk.users.disable_user(uuid=uuid_str)

async def delete_rw_user(sdk, uuid_str: str):
    await sdk.users.delete_user(uuid=uuid_str)

async def main():
    args = parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Resolve env path
    env_path = args.env
    if env_path:
        target_env = Path(env_path)
    else:
        # Try bot/.env first, then server_manager/.env
        if (bot_dir / ".env").exists():
            target_env = bot_dir / ".env"
        elif (backend_dir / "server_manager" / ".env").exists():
            target_env = backend_dir / "server_manager" / ".env"
        else:
            target_env = Path(".env")

    if target_env.exists():
        load_dotenv(target_env)
        logger.info(f"Loaded environment from {target_env}")
    else:
        logger.warning(f"Environment file {target_env} not found, relying on system env.")

    # Import modules now that env vars are loaded
    try:
        from firebase_admin import firestore
        from mvm_bot.firebase_client import init_firebase
        from mvm_bot.datetime_utils import as_utc_datetime
        from mvm_bot.config import remnawave_internal_squad_uuid
        from mvm_bot.user_service.remnawave import build_user_description
        from remnawave import RemnawaveSDK
    except ImportError as e:
        logger.error(f"Failed to import dependencies: {e}. Are you inside the correct virtual environment?")
        sys.exit(1)

    base_url = os.getenv("REMNAWAVE_BASE_URL")
    api_token = os.getenv("REMNAWAVE_API_TOKEN")

    if not base_url or not api_token:
        logger.error("REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN must be set in env or .env file.")
        sys.exit(1)

    logger.info("Initializing Firebase and Remnawave SDK...")
    db = init_firebase()
    sdk = RemnawaveSDK(base_url=base_url, token=api_token)

    logger.info("Fetching Firebase users...")
    users_ref = db.collection("users")
    fb_snaps = await asyncio.to_thread(lambda: list(users_ref.stream()))
    logger.info(f"Loaded {len(fb_snaps)} users from Firestore.")

    logger.info("Fetching Remnawave users...")
    rw_users = await list_all_remnawave_users(sdk)
    logger.info(f"Loaded {len(rw_users)} users from Remnawave.")

    # Build lookup maps for Remnawave users
    rw_by_username = {}
    rw_by_uuid = {}
    rw_by_telegram_id = {}

    for u in rw_users:
        if u.username:
            rw_by_username[u.username.lower()] = u
        if u.uuid:
            rw_by_uuid[str(u.uuid)] = u
        if u.telegram_id:
            rw_by_telegram_id[int(u.telegram_id)] = u

    fb_user_ids = set()
    synced_count = 0
    created_count = 0
    updated_count = 0

    for snap in fb_snaps:
        user_uid = snap.id
        fb_user_ids.add(user_uid)
        user_data = snap.to_dict() or {}

        # 1. Parse target expiration
        ends_at = as_utc_datetime(user_data.get("subscriptionEndsAt"))
        now = datetime.now(timezone.utc)
        target_status = "ACTIVE" if ends_at and ends_at > now else "DISABLED"
        if ends_at is None:
            ends_at = now

        # 2. Extract Telegram ID
        tg_id = None
        ext_tg = user_data.get("externalTg")
        if ext_tg:
            if isinstance(ext_tg, str):
                if ext_tg.startswith("tg:"):
                    try:
                        tg_id = int(ext_tg.split(":", 1)[1])
                    except ValueError:
                        pass
                else:
                    try:
                        tg_id = int(ext_tg)
                    except ValueError:
                        pass
            elif isinstance(ext_tg, int):
                tg_id = ext_tg

        # 3. Match candidate usernames
        username_std = f"mvm-{user_uid.replace('-', '')}"
        username_old = f"mvm-{user_uid}"
        firebase_rw_uuid = user_data.get("remnawaveUuid")

        matched_rw_user = None

        if username_std.lower() in rw_by_username:
            matched_rw_user = rw_by_username[username_std.lower()]
        elif username_old.lower() in rw_by_username:
            matched_rw_user = rw_by_username[username_old.lower()]
        elif firebase_rw_uuid and firebase_rw_uuid in rw_by_uuid:
            matched_rw_user = rw_by_uuid[firebase_rw_uuid]
        elif tg_id is not None and tg_id in rw_by_telegram_id:
            matched_rw_user = rw_by_telegram_id[tg_id]

        if matched_rw_user:
            # Sync existing user
            rw_expire_at = parse_rw_datetime(matched_rw_user.expire_at)
            rw_status = str(matched_rw_user.status).upper()

            if target_status == "ACTIVE":
                status_diff = (rw_status != "ACTIVE")
            else:
                # Any non-ACTIVE status (EXPIRED, LIMITED, DISABLED) on the panel
                # when we want DISABLED means we only need to act if it's ACTIVE.
                status_diff = (rw_status == "ACTIVE")

            tg_diff = False
            if tg_id is not None and matched_rw_user.telegram_id != tg_id:
                tg_diff = True

            exp_diff = False
            # Only sync/check expiration date if the target status is ACTIVE.
            # (Remnawave auto-sets EXPIRED for past expiry dates; we never send
            # a past expire_at in PATCH to avoid triggering that.)
            if target_status == "ACTIVE":
                if rw_expire_at is None:
                    exp_diff = True
                else:
                    if abs((rw_expire_at - ends_at).total_seconds()) > 5:
                        exp_diff = True

            target_description = await build_user_description(user_uid, user_data)
            desc_diff = (matched_rw_user.description != target_description)

            needs_rw_update = status_diff or tg_diff or exp_diff or desc_diff
            if needs_rw_update:
                if not args.dry_run:
                    try:
                        await update_rw_user(
                            sdk,
                            uuid_str=str(matched_rw_user.uuid),
                            current_status_str=rw_status,
                            target_status_str=target_status,
                            expire_at=ends_at if target_status == "ACTIVE" else None,
                            telegram_id=tg_id,
                            description=target_description
                        )
                        logger.info(f"Updated Remnawave user '{matched_rw_user.username}' (UUID: {matched_rw_user.uuid})")
                    except Exception as e:
                        logger.error(f"Failed to update Remnawave user '{matched_rw_user.username}': {e}")
                else:
                    logger.info(f"[Dry Run] Would update Remnawave user '{matched_rw_user.username}': status={target_status}, expiry={ends_at if target_status == 'ACTIVE' else 'unchanged'}, description={target_description}")
                updated_count += 1

            # Sync subscription link and UUID to Firestore
            needs_fb_update = (
                firebase_rw_uuid != str(matched_rw_user.uuid) or
                user_data.get("remnawaveShortUuid") != str(matched_rw_user.short_uuid) or
                normalize_sub_url(user_data.get("remnawaveSubscriptionUrl")) != normalize_sub_url(str(matched_rw_user.subscription_url))
            )

            if needs_fb_update:
                if True:
                    await asyncio.to_thread(
                        lambda: users_ref.document(user_uid).update({
                            "remnawaveUuid": str(matched_rw_user.uuid),
                            "remnawaveShortUuid": str(matched_rw_user.short_uuid),
                            "remnawaveSubscriptionUrl": str(matched_rw_user.subscription_url),
                            "updatedAt": firestore.SERVER_TIMESTAMP
                        })
                    )
                    logger.info(f"Updated Firestore fields for user '{user_uid}' to match Remnawave panel.")
                else:
                    logger.info(f"[Dry Run] Would update Firestore for user '{user_uid}': remnawaveUuid={matched_rw_user.uuid}, remnawaveSubscriptionUrl={matched_rw_user.subscription_url}")
                updated_count += 1
            
            synced_count += 1
        else:
            # Create missing user
            # If active, set expire_at to ends_at.
            # If disabled, set it to a safe future date to pass Remnawave's "not in the past" validation.
            rw_expire_at = ends_at if target_status == "ACTIVE" else now + timedelta(minutes=10)
            target_description = await build_user_description(user_uid, user_data)

            if not args.dry_run:
                resp = await create_rw_user(
                    sdk,
                    username=username_std,
                    expire_at=rw_expire_at,
                    status_str=target_status,
                    telegram_id=tg_id,
                    squad_uuid_str=remnawave_internal_squad_uuid(),
                    description=target_description
                )
                rw_uuid = str(resp.uuid)
                rw_short = str(resp.short_uuid)
                rw_sub_url = str(resp.subscription_url)

                await asyncio.to_thread(
                    lambda: users_ref.document(user_uid).update({
                        "remnawaveUuid": rw_uuid,
                        "remnawaveShortUuid": rw_short,
                        "remnawaveSubscriptionUrl": rw_sub_url,
                        "updatedAt": firestore.SERVER_TIMESTAMP
                    })
                )
                logger.info(f"Created Remnawave user '{username_std}' (UUID: {rw_uuid}) and updated Firestore.")
            else:
                logger.info(f"[Dry Run] Would create Remnawave user '{username_std}': status={target_status}, expiry={rw_expire_at}, telegram_id={tg_id}, description={target_description}")
            created_count += 1
            synced_count += 1

    # Identify orphaned users
    orphans_count = 0
    fb_user_ids_no_hyphens = {uid.replace("-", "").lower(): uid for uid in fb_user_ids}
    fb_user_ids_with_hyphens = {uid.lower(): uid for uid in fb_user_ids}

    for u in rw_users:
        username = u.username
        if not username or not username.lower().startswith("mvm-"):
            continue

        suffix = username[4:].lower()
        is_orphan = (suffix not in fb_user_ids_no_hyphens) and (suffix not in fb_user_ids_with_hyphens)

        if is_orphan:
            orphans_count += 1
            logger.warning(f"Orphaned user found on panel: '{username}' (UUID: {u.uuid})")
            if args.cleanup_action == "disable":
                if not args.dry_run:
                    await disable_rw_user(sdk, str(u.uuid))
                    logger.info(f"Disabled orphaned user '{username}' (UUID: {u.uuid})")
                else:
                    logger.info(f"[Dry Run] Would disable orphaned user '{username}' (UUID: {u.uuid})")
            elif args.cleanup_action == "delete":
                if not args.dry_run:
                    await delete_rw_user(sdk, str(u.uuid))
                    logger.info(f"Deleted orphaned user '{username}' (UUID: {u.uuid})")
                else:
                    logger.info(f"[Dry Run] Would delete orphaned user '{username}' (UUID: {u.uuid})")

    logger.info("Sync complete. Summary:")
    logger.info(f"  Processed Users: {len(fb_snaps)}")
    logger.info(f"  Created: {created_count}")
    logger.info(f"  Updated: {updated_count}")
    logger.info(f"  Orphans Detected: {orphans_count} (Action: {args.cleanup_action})")

if __name__ == "__main__":
    asyncio.run(main())
