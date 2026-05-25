import logging
import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set, List

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot_admin.config import admin_telegram_ids
from bot_admin.firebase_client import init_firestore

logger = logging.getLogger(__name__)
router = Router(name="statistics")

# Standard subscription plans pricing fallback
PLAN_PRICES = {
    "plan_30": 50.0,
    "plan_90": 150.0,
    "plan_180": 300.0,
}

HELEKET_ORDER_ID_RE = re.compile(r"^mvm-(tg|vk)-(\d+)-(plan_\d+)-([a-zA-Z0-9]+)$")


def _is_admin(user_id: Optional[int]) -> bool:
    if user_id is None:
        return False
    return user_id in admin_telegram_ids()


def parse_heleket_order_id(order_id: Optional[str]) -> Optional[Dict[str, str]]:
    if not order_id:
        return None
    match = HELEKET_ORDER_ID_RE.match(order_id.strip())
    if match:
        return {
            "provider": match.group(1),
            "externalUserId": match.group(2),
            "planKey": match.group(3),
        }
    return None


def get_amount(doc_data: Dict[str, Any], plan_key: Optional[str] = None) -> float:
    # Try retrieving amount field
    amount_val = doc_data.get("amount")
    if amount_val is not None:
        try:
            return float(amount_val)
        except (ValueError, TypeError):
            pass

    # Fallback to planKey pricing
    p_key = plan_key or doc_data.get("planKey")
    if p_key in PLAN_PRICES:
        return PLAN_PRICES[p_key]

    return 0.0


def fetch_raw_data(db: Any, start_time: datetime) -> Dict[str, List[Dict[str, Any]]]:
    """Fetches all raw user and purchase data from Firestore since start_time."""
    users = db.collection("users").where("createdAt", ">=", start_time).stream()
    clicks = db.collection("payment_checkout_clicks").where("createdAt", ">=", start_time).stream()
    freekassa = db.collection("freekassa_processed").where("processedAt", ">=", start_time).stream()
    platega = db.collection("platega_processed").where("processedAt", ">=", start_time).stream()
    heleket = db.collection("heleket_processed").where("processedAt", ">=", start_time).stream()
    yoomoney = db.collection("yoomoney_processed").where("processedAt", ">=", start_time).stream()

    return {
        "users": [d.to_dict() for d in users],
        "clicks": [d.to_dict() for d in clicks],
        "freekassa": [d.to_dict() for d in freekassa],
        "platega": [d.to_dict() for d in platega],
        "heleket": [d.to_dict() for d in heleket],
        "yoomoney": [d.to_dict() for d in yoomoney],
    }


def filter_by_age(items: List[Dict[str, Any]], field_name: str, cutoff: datetime) -> List[Dict[str, Any]]:
    """Filters a list of dictionaries by datetime field being >= cutoff."""
    filtered = []
    for item in items:
        val = item.get(field_name)
        if not val:
            continue
        
        if isinstance(val, datetime):
            dt = val
        else:
            try:
                # Fallback if stored as ISO string
                dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except ValueError:
                continue

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        if dt >= cutoff:
            filtered.append(item)
    return filtered


def calculate_period_stats(data: Dict[str, List[Dict[str, Any]]], cutoff: datetime) -> Dict[str, Any]:
    """Calculates statistics for a subset of data starting from cutoff."""
    period_users = filter_by_age(data["users"], "createdAt", cutoff)
    period_clicks = filter_by_age(data["clicks"], "createdAt", cutoff)
    period_freekassa = filter_by_age(data["freekassa"], "processedAt", cutoff)
    period_platega = filter_by_age(data["platega"], "processedAt", cutoff)
    period_heleket = filter_by_age(data["heleket"], "processedAt", cutoff)
    period_yoomoney = filter_by_age(data["yoomoney"], "processedAt", cutoff)

    purchases_count = 0
    revenue = 0.0
    unique_buyers: Set[str] = set()

    # FreeKassa stats
    freekassa_revenue = 0.0
    for p in period_freekassa:
        purchases_count += 1
        amount = get_amount(p)
        revenue += amount
        freekassa_revenue += amount
        buyer = p.get("externalUserId") or p.get("providerField") or "unknown"
        unique_buyers.add(f"freekassa:{buyer}")

    # Platega stats
    platega_revenue = 0.0
    for p in period_platega:
        purchases_count += 1
        amount = get_amount(p)
        revenue += amount
        platega_revenue += amount
        buyer = p.get("externalUserId") or "unknown"
        unique_buyers.add(f"platega:{buyer}")

    # Heleket stats
    heleket_revenue = 0.0
    for p in period_heleket:
        purchases_count += 1
        parsed = parse_heleket_order_id(p.get("orderId"))
        plan_key = p.get("planKey")
        amount = get_amount(p, plan_key)
        revenue += amount
        heleket_revenue += amount
        if parsed:
            buyer = parsed.get("externalUserId") or "unknown"
            unique_buyers.add(f"heleket:{buyer}")
        else:
            unique_buyers.add(f"heleket_unknown:{p.get('orderId', '')}")

    # YooMoney stats
    yoomoney_revenue = 0.0
    for p in period_yoomoney:
        purchases_count += 1
        amount = get_amount(p)
        revenue += amount
        yoomoney_revenue += amount
        buyer = p.get("externalUserId") or "unknown"
        unique_buyers.add(f"yoomoney:{buyer}")

    new_users_count = len(period_users)
    checkout_clicks_count = len(period_clicks)
    unique_buyers_count = len(unique_buyers)

    # Conversion 1: click to purchase (Purchases / checkout clicks)
    click_conversion = 0.0
    if checkout_clicks_count > 0:
        click_conversion = (purchases_count / checkout_clicks_count) * 100.0

    # Conversion 2: registration to purchase (New paying users / New registered users)
    # Collect all external IDs of users registered in this period
    new_user_external_ids: Set[str] = set()
    for u in period_users:
        tg = u.get("externalTg")
        if tg:
            new_user_external_ids.add(str(tg))
            if tg.startswith("tg:"):
                new_user_external_ids.add(tg[3:])
        vk = u.get("externalVk")
        if vk:
            new_user_external_ids.add(str(vk))
            if vk.startswith("vk:"):
                new_user_external_ids.add(vk[3:])
        apple = u.get("externalAppleId")
        if apple:
            new_user_external_ids.add(str(apple))

    purchasing_new_users: Set[str] = set()
    for p in period_freekassa:
        buyer = p.get("externalUserId")
        if buyer and str(buyer) in new_user_external_ids:
            purchasing_new_users.add(str(buyer))

    for p in period_platega:
        buyer = p.get("externalUserId")
        if buyer and str(buyer) in new_user_external_ids:
            purchasing_new_users.add(str(buyer))

    for p in period_heleket:
        parsed = parse_heleket_order_id(p.get("orderId"))
        if parsed:
            buyer = parsed.get("externalUserId")
            if buyer and str(buyer) in new_user_external_ids:
                purchasing_new_users.add(str(buyer))

    for p in period_yoomoney:
        buyer = p.get("externalUserId")
        if buyer and str(buyer) in new_user_external_ids:
            purchasing_new_users.add(str(buyer))

    user_conversion = 0.0
    if new_users_count > 0:
        user_conversion = (len(purchasing_new_users) / new_users_count) * 100.0

    # ARPU: Revenue per registered user
    arpu = 0.0
    if new_users_count > 0:
        arpu = revenue / new_users_count

    # ARPPU: Revenue per buyer
    arppu = 0.0
    if unique_buyers_count > 0:
        arppu = revenue / unique_buyers_count

    return {
        "purchases_count": purchases_count,
        "revenue": revenue,
        "new_users_count": new_users_count,
        "checkout_clicks_count": checkout_clicks_count,
        "unique_buyers_count": unique_buyers_count,
        "click_conversion": click_conversion,
        "user_conversion": user_conversion,
        "arpu": arpu,
        "arppu": arppu,
        "freekassa_revenue": freekassa_revenue,
        "platega_revenue": platega_revenue,
        "heleket_revenue": heleket_revenue,
        "yoomoney_revenue": yoomoney_revenue,
        "freekassa_count": len(period_freekassa),
        "platega_count": len(period_platega),
        "heleket_count": len(period_heleket),
        "yoomoney_count": len(period_yoomoney),
    }


def format_stats_block(label: str, s: Dict[str, Any]) -> str:
    return (
        f"📅 <b>Период: {label}</b>\n\n"
        f"💵 <b>Выручка:</b> <code>{s['revenue']:.2f} RUB</code>\n"
        f"  • FreeKassa: <code>{s['freekassa_revenue']:.2f} RUB</code> ({s['freekassa_count']} шт)\n"
        f"  • YooMoney: <code>{s['yoomoney_revenue']:.2f} RUB</code> ({s['yoomoney_count']} шт)\n"
        f"  • Platega: <code>{s['platega_revenue']:.2f} RUB</code> ({s['platega_count']} шт)\n"
        f"  • Heleket: <code>{s['heleket_revenue']:.2f} RUB</code> ({s['heleket_count']} шт)\n\n"
        f"🛍️ <b>Покупки:</b> {s['purchases_count']} шт\n"
        f"👤 <b>Покупатели:</b> {s['unique_buyers_count']}\n"
        f"🆕 <b>Новые юзеры:</b> {s['new_users_count']}\n"
        f"🖱️ <b>Клики на оплату:</b> {s['checkout_clicks_count']}\n\n"
        f"📈 <b>Конверсия:</b>\n"
        f"  • Клик ➔ Оплата: <code>{s['click_conversion']:.1f}%</code>\n"
        f"  • Рег ➔ Оплата: <code>{s['user_conversion']:.1f}%</code>\n\n"
        f"💰 <b>Доход на юзера:</b>\n"
        f"  • ARPU (на рег.): <code>{s['arpu']:.2f} RUB</code>\n"
        f"  • ARPPU (на покуп.): <code>{s['arppu']:.2f} RUB</code>"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return

    status_msg = await message.answer("📊 Собираю статистику... Это может занять несколько секунд.")

    try:
        now = datetime.now(timezone.utc)
        # Fetch 7 days of data at once to query Firestore efficiently
        start_time = now - timedelta(days=7)

        db = init_firestore()
        # Query Firestore in a separate thread because the SDK is blocking
        raw_data = await asyncio.to_thread(fetch_raw_data, db, start_time)

        # Calculate metrics for each window in memory
        stats_24h = calculate_period_stats(raw_data, now - timedelta(days=1))
        stats_3d = calculate_period_stats(raw_data, now - timedelta(days=3))
        stats_7d = calculate_period_stats(raw_data, now - timedelta(days=7))

        response_text = "📊 <b>АНАЛИТИКА И СТАТИСТИКА</b>\n\n"
        response_text += format_stats_block("24 ЧАСА", stats_24h)
        response_text += "\n" + "—" * 20 + "\n\n"
        response_text += format_stats_block("3 ДНЯ", stats_3d)
        response_text += "\n" + "—" * 20 + "\n\n"
        response_text += format_stats_block("7 ДНЕЙ", stats_7d)

        await status_msg.edit_text(response_text, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to compute statistics")
        await status_msg.edit_text(f"❌ Не удалось получить статистику: {e}")
