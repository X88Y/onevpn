import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot_admin.config import admin_telegram_ids
from bot_admin.firebase_client import init_firestore
from bot_admin.handlers.statistics import (
    fetch_raw_data,
    filter_by_age,
    get_amount,
    parse_heleket_order_id,
    parse_datetime,
)

logger = logging.getLogger(__name__)
router = Router(name="group_statistics")

TELEGRAM_TEXT_LIMIT = 3500
VK_API_VERSION = "5.199"
VK_GROUPS_BATCH_SIZE = 500


@dataclass
class VkGroupInfo:
    group_id: str
    name: str
    url: str


@dataclass
class GroupStats:
    registrations: int = 0
    purchases_count: int = 0
    revenue: float = 0.0
    paying_users: Set[str] = field(default_factory=set)
    paying_new_users: Set[str] = field(default_factory=set)


def _is_admin(user_id: Optional[int]) -> bool:
    if user_id is None:
        return False
    return user_id in admin_telegram_ids()


def get_user_group_ids(user: Dict[str, Any]) -> List[str]:
    group_ids = user.get("vkGroupIds")
    if isinstance(group_ids, list) and group_ids:
        return [str(gid) for gid in group_ids if gid is not None and str(gid).strip()]
    single = user.get("vkGroupId")
    if single is not None and str(single).strip():
        return [str(single)]
    return []


def external_id_lookup_keys(user: Dict[str, Any]) -> Set[str]:
    keys: Set[str] = set()
    for field_name in ("externalTg", "externalVk", "externalAppleId"):
        value = user.get(field_name)
        if not value:
            continue
        raw = str(value)
        keys.add(raw)
        if ":" in raw:
            keys.add(raw.split(":", 1)[1])
    return keys


def buyer_lookup_keys(provider: str, external_user_id: str) -> Set[str]:
    buyer = str(external_user_id).strip()
    if not buyer:
        return set()
    keys = {buyer, f"{provider}:{buyer}"}
    if buyer.startswith(f"{provider}:"):
        keys.add(buyer.split(":", 1)[1])
    return keys


def fetch_users_with_groups(db: Any) -> List[Dict[str, Any]]:
    users: List[Dict[str, Any]] = []
    for doc in db.collection("users").stream():
        data = doc.to_dict() or {}
        group_ids = get_user_group_ids(data)
        if not group_ids:
            continue
        users.append(data)
    return users


def default_group_url(group_id: str) -> str:
    return f"https://vk.com/club{group_id}"


def build_group_url(group_id: str, screen_name: Optional[str]) -> str:
    if screen_name:
        cleaned = str(screen_name).strip()
        if cleaned:
            return f"https://vk.com/{cleaned}"
    return default_group_url(group_id)


def fetch_vk_group_tokens(db: Any) -> Dict[str, str]:
    tokens: Dict[str, str] = {}
    for doc in db.collection("vk_tokens").stream():
        data = doc.to_dict() or {}
        if data.get("status") == "inactive":
            continue
        token = data.get("token")
        group_id = data.get("group_id")
        if not token or group_id is None:
            continue
        tokens[str(group_id).strip()] = str(token).strip()
    return tokens


def _vk_groups_get_by_id(token: str, group_ids: List[str]) -> List[Dict[str, Any]]:
    if not group_ids:
        return []

    params = {
        "access_token": token,
        "v": VK_API_VERSION,
        "fields": "screen_name",
    }
    if len(group_ids) == 1:
        params["group_id"] = group_ids[0]
    else:
        params["group_ids"] = ",".join(group_ids)

    try:
        response = httpx.post(
            "https://api.vk.com/method/groups.getById",
            data=params,
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        logger.exception("VK groups.getById request failed for groups %s", group_ids[:5])
        return []

    if "error" in payload:
        logger.warning("VK groups.getById error: %s", payload["error"])
        return []

    raw = payload.get("response")
    if isinstance(raw, dict):
        groups = raw.get("groups", [])
    elif isinstance(raw, list):
        groups = raw
    else:
        groups = []
    return [group for group in groups if isinstance(group, dict)]


def _parse_vk_groups(groups: List[Dict[str, Any]]) -> Dict[str, VkGroupInfo]:
    info: Dict[str, VkGroupInfo] = {}
    for group in groups:
        group_id = group.get("id")
        if group_id is None:
            continue
        gid = str(group_id).strip()
        name = str(group.get("name") or f"Group {gid}").strip()
        screen_name = group.get("screen_name")
        info[gid] = VkGroupInfo(
            group_id=gid,
            name=name,
            url=build_group_url(gid, str(screen_name) if screen_name else None),
        )
    return info


def fetch_vk_groups_info(
    group_ids: Set[str],
    group_tokens: Dict[str, str],
) -> Dict[str, VkGroupInfo]:
    info: Dict[str, VkGroupInfo] = {}
    remaining = {gid for gid in group_ids if gid}

    for group_id in list(remaining):
        token = group_tokens.get(group_id)
        if not token:
            continue
        parsed = _parse_vk_groups(_vk_groups_get_by_id(token, [group_id]))
        if group_id in parsed:
            info[group_id] = parsed[group_id]
            remaining.discard(group_id)

    fallback_tokens = list(dict.fromkeys(group_tokens.values()))
    if remaining and fallback_tokens:
        token = fallback_tokens[0]
        pending = list(remaining)
        for offset in range(0, len(pending), VK_GROUPS_BATCH_SIZE):
            batch = pending[offset : offset + VK_GROUPS_BATCH_SIZE]
            parsed = _parse_vk_groups(_vk_groups_get_by_id(token, batch))
            info.update(parsed)
            for group_id in batch:
                if group_id in parsed:
                    remaining.discard(group_id)

    for group_id in remaining:
        info[group_id] = VkGroupInfo(
            group_id=group_id,
            name=f"Group {group_id}",
            url=default_group_url(group_id),
        )
    return info


def build_user_lookup(users: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for user in users:
        for key in external_id_lookup_keys(user):
            lookup[key] = user
    return lookup


def resolve_purchase_buyer(payment: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    parsed = parse_heleket_order_id(payment.get("orderId"))
    if parsed:
        provider = parsed.get("provider") or "tg"
        external_user_id = parsed.get("externalUserId")
        if external_user_id:
            return provider, str(external_user_id)

    provider = str(payment.get("provider") or "tg")
    external_user_id = payment.get("externalUserId")
    if external_user_id:
        return provider, str(external_user_id)
    return None


def lookup_user(
    user_lookup: Dict[str, Dict[str, Any]],
    provider: str,
    external_user_id: str,
) -> Optional[Dict[str, Any]]:
    for key in buyer_lookup_keys(provider, external_user_id):
        user = user_lookup.get(key)
        if user is not None:
            return user
    return None


def purchase_amount(payment: Dict[str, Any]) -> float:
    parsed = parse_heleket_order_id(payment.get("orderId"))
    plan_key = payment.get("planKey")
    if plan_key is None and parsed:
        plan_key = parsed.get("planKey")
    return get_amount(payment, plan_key)


def collect_period_purchases(
    raw_data: Dict[str, List[Dict[str, Any]]],
    cutoff: datetime,
) -> List[Dict[str, Any]]:
    purchases: List[Dict[str, Any]] = []
    for collection_name in ("freekassa", "platega", "heleket", "yoomoney"):
        field_name = "processedAt"
        purchases.extend(filter_by_age(raw_data[collection_name], field_name, cutoff))
    return purchases


def calculate_group_stats(
    users_with_groups: List[Dict[str, Any]],
    purchases: List[Dict[str, Any]],
    cutoff: datetime,
) -> Dict[str, GroupStats]:
    stats: Dict[str, GroupStats] = defaultdict(GroupStats)
    user_lookup = build_user_lookup(users_with_groups)

    for user in users_with_groups:
        created_at = parse_datetime(user.get("createdAt"))
        if created_at is None or created_at < cutoff:
            continue
        for group_id in get_user_group_ids(user):
            stats[group_id].registrations += 1

    for payment in purchases:
        buyer = resolve_purchase_buyer(payment)
        if buyer is None:
            continue
        provider, external_user_id = buyer
        user = lookup_user(user_lookup, provider, external_user_id)
        if user is None:
            continue

        group_ids = get_user_group_ids(user)
        if not group_ids:
            continue

        amount = purchase_amount(payment)
        buyer_key = f"{provider}:{external_user_id}"
        created_at = parse_datetime(user.get("createdAt"))
        registered_in_period = created_at is not None and created_at >= cutoff

        for group_id in group_ids:
            group = stats[group_id]
            group.purchases_count += 1
            group.revenue += amount
            group.paying_users.add(buyer_key)
            if registered_in_period:
                group.paying_new_users.add(buyer_key)

    return dict(stats)


def split_telegram_messages(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> List[str]:
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current.rstrip())
            current = line
        else:
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
            current = line

    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def format_group_stats_block(
    label: str,
    stats: Dict[str, GroupStats],
    group_info: Dict[str, VkGroupInfo],
) -> str:
    active_groups = {
        group_id: group
        for group_id, group in stats.items()
        if group.registrations > 0 or group.purchases_count > 0 or group.revenue > 0
    }
    if not active_groups:
        return f"📅 <b>Период: {label}</b>\n\nНет данных по VK-группам."

    sorted_groups = sorted(
        active_groups.items(),
        key=lambda item: (item[1].revenue, item[1].purchases_count, item[1].registrations),
        reverse=True,
    )

    total_regs = sum(group.registrations for _, group in sorted_groups)
    total_purchases = sum(group.purchases_count for _, group in sorted_groups)
    total_revenue = sum(group.revenue for _, group in sorted_groups)

    lines = [
        f"📅 <b>Период: {label}</b>",
        f"Итого групп: <b>{len(sorted_groups)}</b>",
        f"Регистрации: <b>{total_regs}</b>",
        f"Покупки: <b>{total_purchases}</b>",
        f"Выручка: <code>{total_revenue:.2f} RUB</code>",
        "",
    ]

    for group_id, group in sorted_groups:
        conversion = 0.0
        if group.registrations > 0:
            conversion = (len(group.paying_new_users) / group.registrations) * 100.0

        meta = group_info.get(group_id) or VkGroupInfo(
            group_id=group_id,
            name=f"Group {group_id}",
            url=default_group_url(group_id),
        )
        title = f'<a href="{escape(meta.url, quote=True)}">{escape(meta.name)}</a>'

        lines.extend(
            [
                f"🔹 {title}",
                f"  ID: <code>{group_id}</code>",
                f"  URL: <a href=\"{escape(meta.url, quote=True)}\">{escape(meta.url)}</a>",
                f"  Регистрации: <b>{group.registrations}</b>",
                f"  Покупки: <b>{group.purchases_count}</b> шт",
                f"  Выручка: <code>{group.revenue:.2f} RUB</code>",
                f"  Рег ➔ Оплата: <code>{conversion:.1f}%</code>",
                f"  Покупатели: <b>{len(group.paying_users)}</b>",
                "",
            ]
        )

    return "\n".join(lines)


async def send_html_chunks(message: Message, text: str) -> None:
    for chunk in split_telegram_messages(text):
        await message.answer(chunk, parse_mode="HTML")


@router.message(Command("group_stats", "stats_groups"))
async def cmd_group_stats(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return

    status_msg = await message.answer(
        "📊 Собираю статистику по VK-группам... Это может занять несколько секунд."
    )

    try:
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(days=7)

        db = init_firestore()
        users_with_groups, raw_data, group_tokens = await asyncio.gather(
            asyncio.to_thread(fetch_users_with_groups, db),
            asyncio.to_thread(fetch_raw_data, db, start_time),
            asyncio.to_thread(fetch_vk_group_tokens, db),
        )

        stats_24h = calculate_group_stats(
            users_with_groups,
            collect_period_purchases(raw_data, now - timedelta(days=1)),
            now - timedelta(days=1),
        )
        stats_3d = calculate_group_stats(
            users_with_groups,
            collect_period_purchases(raw_data, now - timedelta(days=3)),
            now - timedelta(days=3),
        )
        stats_7d = calculate_group_stats(
            users_with_groups,
            collect_period_purchases(raw_data, now - timedelta(days=7)),
            now - timedelta(days=7),
        )

        periods = [
            ("24 ЧАСА", stats_24h),
            ("3 ДНЯ", stats_3d),
            ("7 ДНЕЙ", stats_7d),
        ]

        all_group_ids: Set[str] = set()
        for _, period_stats in periods:
            all_group_ids.update(period_stats.keys())
        group_info = await asyncio.to_thread(
            fetch_vk_groups_info,
            all_group_ids,
            group_tokens,
        )

        await status_msg.delete()
        await message.answer("📊 <b>СТАТИСТИКА ПО VK-ГРУППАМ</b>", parse_mode="HTML")
        for label, period_stats in periods:
            await send_html_chunks(
                message,
                format_group_stats_block(label, period_stats, group_info),
            )

    except Exception as e:
        logger.exception("Failed to compute group statistics")
        await status_msg.edit_text(f"❌ Не удалось получить статистику по группам: {e}")
