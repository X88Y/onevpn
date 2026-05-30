"""Periodic reorder of Remnawave hosts.

Sorting rules (applied every HOST_REORDER_INTERVAL_S seconds):
  1. By tag priority:
       BALANCER > SPEED_SERVER > RU_SERVER > BYPASS_WL > BYPASS_WL_PREMIUM
       > (other known tags alphabetically) > (no tag)
  2. Within each tag group:
       - BALANCER and RU_SERVER: original view_position preserved (no internal reorder).
       - All other tags: ascending sum of usersOnline across the host's
         associated nodes (least-loaded first).
  3. Tie-breaker: host remark (alphabetical).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional
from uuid import UUID

from server_manager.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tag priority — edit here to change the subscription display order
# ---------------------------------------------------------------------------
_TAG_PRIORITY: List[str] = [
    "BALANCER",
    "SPEED_SERVER",
    "RU_SERVER",
    "BYPASS_WL",
    "BYPASS_WL_PREMIUM",
]
_TAG_ORDER: Dict[str, int] = {tag: i for i, tag in enumerate(_TAG_PRIORITY)}
_UNKNOWN_TAG_BASE: int = len(_TAG_PRIORITY)

# Tags whose internal order is kept as-is (sorted by original view_position)
_STATIC_ORDER_TAGS: frozenset = frozenset({"BALANCER", "RU_SERVER"})


def _tag_sort_key(tag: Optional[str]) -> tuple:
    if not tag:
        return (_UNKNOWN_TAG_BASE + 1, "")
    normalised = tag.upper()
    if normalised in _TAG_ORDER:
        return (_TAG_ORDER[normalised], normalised)
    return (_UNKNOWN_TAG_BASE, normalised)


async def _reorder_once() -> None:
    if not settings.remnawave_base_url or not settings.remnawave_api_token:
        return

    try:
        from remnawave import RemnawaveSDK
        from remnawave.models import ReorderHostRequestDto, ReorderHostItem
    except ImportError:
        logger.warning("remnawave SDK not installed — host reorder skipped")
        return

    sdk = RemnawaveSDK(
        base_url=settings.remnawave_base_url,
        token=settings.remnawave_api_token,
    )

    try:
        # 1. Node user counts
        nodes_resp = await sdk.nodes.get_all_nodes()
        node_users: Dict[UUID, int] = {
            node.uuid: (node.users_online or 0) for node in nodes_resp
        }

        # 2. All hosts
        hosts_resp = await sdk.hosts.get_all_hosts()
        hosts = list(hosts_resp)

        if not hosts:
            return

        # 3. Sort
        def _host_users(h) -> int:
            return sum(node_users.get(nu, 0) for nu in h.nodes)

        def _sort_key(h):
            tag_key = _tag_sort_key(h.tag)
            tag_upper = (h.tag or "").upper()
            if tag_upper in _STATIC_ORDER_TAGS:
                # Preserve original panel order within this tag group
                secondary = (h.view_position, "")
            else:
                # Sort by least-loaded first
                secondary = (_host_users(h), h.remark)
            return (tag_key, secondary)

        hosts.sort(key=_sort_key)

        # 4. Build reorder payload (view_position starts at 1)
        items: List[ReorderHostItem] = [
            ReorderHostItem(view_position=pos, uuid=h.uuid)
            for pos, h in enumerate(hosts, start=1)
        ]

        # Log the new order at DEBUG level
        for item, host in zip(items, hosts):
            logger.debug(
                "reorder_hosts: pos=%d remark=%r tag=%r users=%d",
                item.view_position,
                host.remark,
                host.tag,
                _host_users(host),
            )

        # 5. Apply
        await sdk.hosts.reorder_hosts(ReorderHostRequestDto(hosts=items))
        logger.info(
            "reorder_hosts: applied new order for %d hosts (nodes sampled: %d)",
            len(hosts),
            len(node_users),
        )

    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("reorder_hosts iteration failed")


async def run_host_reorder_loop() -> None:
    if not settings.remnawave_base_url or not settings.remnawave_api_token:
        logger.info("Host reorder disabled: REMNAWAVE_BASE_URL / REMNAWAVE_API_TOKEN not set")
        return

    interval = max(60, getattr(settings, "host_reorder_interval_s", 300))
    logger.info("host_reorder worker started interval=%ss", interval)

    while True:
        await _reorder_once()
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
