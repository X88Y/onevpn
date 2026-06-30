"""Reorder Remnawave hosts by tag priority + live node user count.

Tag priority order (first = shown first in subscription):
    1. SPEED_SERVER
    2. BALANCER
    3. BYPASS_WL
    4. BYPASS_WL_PREMIUM
    5. RU_SERVER
    6. (any other tag / no tag — sorted alphabetically after the above)

Within each tag group, hosts are sorted by the *sum of usersOnline* reported
by the nodes attached to that host (ascending — least-loaded host first).

Usage:
    python reorder_hosts.py                  # dry-run, prints new order
    python reorder_hosts.py --apply          # actually calls reorder API
    python reorder_hosts.py --env /path/.env # load a specific .env file
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import logging
import os
import pkgutil
import sys
import types
import typing
from pathlib import Path
from typing import Dict, List, Optional, Union, get_args, get_origin
from uuid import UUID

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

try:
    from remnawave import RemnawaveSDK
    import remnawave.models
    from remnawave.models import ReorderHostItem, ReorderHostRequestDto
    from remnawave.models.hosts import HostResponseDto
except ImportError:
    RemnawaveSDK = None
    remnawave = None
    ReorderHostItem = None
    ReorderHostRequestDto = None
    HostResponseDto = None


def _is_optional(annotation: typing.Any) -> bool:
    if annotation is type(None):
        return True
    origin = get_origin(annotation)
    if origin is Union or (hasattr(types, "UnionType") and origin is types.UnionType):
        return type(None) in get_args(annotation)
    return False


def _patch_remnawave_models() -> None:
    if remnawave is None or remnawave.models is None or HostResponseDto is None:
        return

    # 1. Inject 'tags' field and 'tag' property into HostResponseDto
    if "tags" not in HostResponseDto.model_fields:
        field_info = FieldInfo(default_factory=list, alias="tags")
        field_info.annotation = List[str]
        HostResponseDto.model_fields["tags"] = field_info

    def get_tag(self: typing.Any) -> typing.Optional[str]:
        tags = getattr(self, "tags", None)
        if tags:
            return tags[0]
        return None

    HostResponseDto.tag = property(get_tag)  # type: ignore

    # 2. Patch all models
    package = remnawave.models
    modules = []
    for _, module_name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        try:
            modules.append(__import__(module_name, fromlist=["*"]))
        except Exception:
            continue

    all_models = []
    for mod in modules:
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, BaseModel) and obj is not BaseModel:
                all_models.append(obj)

    # First, modify all fields across all models
    for obj in all_models:
        for field in obj.model_fields.values():
            if field.default is PydanticUndefined and _is_optional(field.annotation):
                field.default = None

    # Then rebuild all models multiple times to resolve nested schemas
    for _ in range(3):
        for obj in all_models:
            try:
                obj.model_rebuild(force=True)
            except Exception:
                pass


_patch_remnawave_models()


# ---------------------------------------------------------------------------
# Bootstrap: load .env so this script can be run standalone without the
# server_manager package being on PYTHONPATH (but also works inside it).
# ---------------------------------------------------------------------------
def _load_env(env_path: Optional[str] = None) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    if env_path:
        load_dotenv(env_path, override=True)
        return

    # Walk up looking for .env
    candidates = [
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent / "server_manager" / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p, override=True)
            return


# ---------------------------------------------------------------------------
# Tag priority — add / reorder as needed
# ---------------------------------------------------------------------------
TAG_PRIORITY: List[str] = [
    "SPEED_SERVER",
    "BALANCER",
    "BYPASS_WL",
    "BYPASS_WL_PREMIUM",
    "RU_SERVER",
]

_TAG_ORDER: Dict[str, int] = {tag: i for i, tag in enumerate(TAG_PRIORITY)}
_UNKNOWN_TAG_BASE = len(TAG_PRIORITY)  # unknown tags come after the known ones

# Tags whose internal order is preserved (not sorted by user count)
_STATIC_ORDER_TAGS: frozenset = frozenset({"BALANCER", "RU_SERVER"})

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _tag_sort_key(tag: Optional[str]) -> tuple:
    """Returns a sort key (priority_index, tag_string) for a host's tag."""
    if not tag:
        return (_UNKNOWN_TAG_BASE + 1, "")
    normalised = tag.upper()
    if normalised in _TAG_ORDER:
        return (_TAG_ORDER[normalised], normalised)
    # Unknown tag: comes after known ones, sorted alphabetically among themselves
    return (_UNKNOWN_TAG_BASE, normalised)


async def reorder(*, apply: bool, env_path: Optional[str]) -> None:
    _load_env(env_path)

    base_url = os.getenv("REMNAWAVE_BASE_URL") or os.getenv("REMNAWAVE_URL")
    api_token = os.getenv("REMNAWAVE_API_TOKEN") or os.getenv("REMNAWAVE_TOKEN")

    if not base_url or not api_token:
        logger.error(
            "REMNAWAVE_BASE_URL and REMNAWAVE_API_TOKEN must be set "
            "(via environment or .env file)"
        )
        sys.exit(1)

    if RemnawaveSDK is None or ReorderHostRequestDto is None or ReorderHostItem is None:
        logger.error("remnawave SDK not installed. Run: pip install remnawave")
        sys.exit(1)

    sdk = RemnawaveSDK(base_url=base_url, token=api_token)

    # ------------------------------------------------------------------
    # 1. Fetch nodes and build uuid → users_online map
    # ------------------------------------------------------------------
    logger.info("Fetching nodes from Remnawave…")
    nodes_resp = await sdk.nodes.get_all_nodes()
    node_users: Dict[UUID, int] = {}
    for node in nodes_resp:
        count = node.users_online or 0
        node_users[node.uuid] = count
        logger.debug("  node %s (%s) → %d users online", node.uuid, node.name, count)

    logger.info("Found %d nodes", len(node_users))

    # ------------------------------------------------------------------
    # 2. Fetch hosts
    # ------------------------------------------------------------------
    logger.info("Fetching hosts from Remnawave…")
    hosts_resp = await sdk.hosts.get_all_hosts()
    hosts = list(hosts_resp)
    logger.info("Found %d hosts", len(hosts))

    # ------------------------------------------------------------------
    # 3. Sort hosts: primary = tag priority, secondary = total users online
    # ------------------------------------------------------------------
    def _host_total_users(host) -> int:
        return sum(node_users.get(node_uuid, 0) for node_uuid in host.nodes)

    def _sort_key(host):
        tag_key = _tag_sort_key(host.tag)
        tag_upper = (host.tag or "").upper()
        if tag_upper in _STATIC_ORDER_TAGS:
            secondary = (host.view_position, "")
        else:
            secondary = (_host_total_users(host), host.remark)
        return (tag_key, secondary)

    hosts.sort(key=_sort_key)

    # ------------------------------------------------------------------
    # 4. Print the new order
    # ------------------------------------------------------------------
    logger.info("\n=== New host order ===")
    reorder_items: List[ReorderHostItem] = []
    for new_pos, host in enumerate(hosts, start=1):
        total_users = _host_total_users(host)
        tag_display = host.tag or "(no tag)"
        logger.info(
            "  [%3d] %-32s  tag=%-20s  users_online=%d  uuid=%s",
            new_pos,
            host.remark,
            tag_display,
            total_users,
            host.uuid,
        )
        reorder_items.append(ReorderHostItem(view_position=new_pos, uuid=host.uuid))

    # ------------------------------------------------------------------
    # 5. Apply if requested
    # ------------------------------------------------------------------
    if not apply:
        logger.info(
            "\nDry-run mode — no changes made. "
            "Run with --apply to persist the new order."
        )
        return

    logger.info("\nApplying new order via Remnawave API…")
    result = await sdk.hosts.reorder_hosts(
        ReorderHostRequestDto(hosts=reorder_items)
    )
    if getattr(result, "is_updated", True):
        logger.info("✓ Hosts reordered successfully.")
    else:
        logger.warning("Reorder call returned is_updated=False — check the panel.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reorder Remnawave hosts by tag priority + live node user count"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply the new order (default: dry-run only)",
    )
    parser.add_argument(
        "--env",
        metavar="FILE",
        default=None,
        help="Path to a .env file to load (default: auto-detect)",
    )
    args = parser.parse_args()
    asyncio.run(reorder(apply=args.apply, env_path=args.env))


if __name__ == "__main__":
    main()
