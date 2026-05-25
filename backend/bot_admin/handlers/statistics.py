import logging
import asyncio
import re
import io
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set, List

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile

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


def parse_datetime(val: Any) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        dt = val
    else:
        try:
            dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def filter_in_bin(items: List[Dict[str, Any]], field_name: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    filtered = []
    for item in items:
        val = item.get(field_name)
        if not val:
            continue
        dt = parse_datetime(val)
        if dt and start <= dt < end:
            filtered.append(item)
    return filtered


def generate_daily_bins(start_time: datetime, end_time: datetime) -> List[tuple[datetime, datetime]]:
    # Align start_time to 00:00:00 UTC of that day
    start_aligned = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
    
    bins = []
    current = start_aligned
    while current < end_time:
        next_day = current + timedelta(days=1)
        bins.append((current, next_day))
        current = next_day
    return bins


def calculate_daily_chart_data(raw_data: Dict[str, List[Dict[str, Any]]], bins: List[tuple[datetime, datetime]]) -> Dict[str, List[Any]]:
    labels = []
    registrations = []
    earnings = []
    click_conversions = []
    user_conversions = []
    
    for bin_start, bin_end in bins:
        label = bin_start.strftime("%d %b")  # e.g. "21 May"
        labels.append(label)
        
        # Filter items in the bin
        bin_users = filter_in_bin(raw_data["users"], "createdAt", bin_start, bin_end)
        bin_clicks = filter_in_bin(raw_data["clicks"], "createdAt", bin_start, bin_end)
        bin_freekassa = filter_in_bin(raw_data["freekassa"], "processedAt", bin_start, bin_end)
        bin_platega = filter_in_bin(raw_data["platega"], "processedAt", bin_start, bin_end)
        bin_heleket = filter_in_bin(raw_data["heleket"], "processedAt", bin_start, bin_end)
        bin_yoomoney = filter_in_bin(raw_data["yoomoney"], "processedAt", bin_start, bin_end)
        
        # Registrations
        reg_count = len(bin_users)
        registrations.append(reg_count)
        
        # Earnings
        total_earn = 0.0
        total_earn += sum(get_amount(p) for p in bin_freekassa)
        total_earn += sum(get_amount(p) for p in bin_platega)
        total_earn += sum(get_amount(p, p.get("planKey")) for p in bin_heleket)
        total_earn += sum(get_amount(p) for p in bin_yoomoney)
        earnings.append(total_earn)
        
        # Purchases Count
        purchases_count = len(bin_freekassa) + len(bin_platega) + len(bin_heleket) + len(bin_yoomoney)
        
        # Click-to-Pay Conversion
        click_count = len(bin_clicks)
        click_conv = (purchases_count / click_count * 100.0) if click_count > 0 else 0.0
        click_conversions.append(click_conv)
        
        # Reg-to-Pay Conversion
        # 1. New user external IDs in this bin
        new_user_external_ids = set()
        for u in bin_users:
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
        
        # 2. Count new users who made a purchase in this bin
        purchasing_new_users = set()
        for p in bin_freekassa:
            buyer = p.get("externalUserId")
            if buyer and str(buyer) in new_user_external_ids:
                purchasing_new_users.add(str(buyer))
        for p in bin_platega:
            buyer = p.get("externalUserId")
            if buyer and str(buyer) in new_user_external_ids:
                purchasing_new_users.add(str(buyer))
        for p in bin_heleket:
            parsed = parse_heleket_order_id(p.get("orderId"))
            if parsed:
                buyer = parsed.get("externalUserId")
                if buyer and str(buyer) in new_user_external_ids:
                    purchasing_new_users.add(str(buyer))
        for p in bin_yoomoney:
            buyer = p.get("externalUserId")
            if buyer and str(buyer) in new_user_external_ids:
                purchasing_new_users.add(str(buyer))
                
        user_conv = (len(purchasing_new_users) / reg_count * 100.0) if reg_count > 0 else 0.0
        user_conversions.append(user_conv)
        
    return {
        "labels": labels,
        "registrations": registrations,
        "earnings": earnings,
        "click_conversions": click_conversions,
        "user_conversions": user_conversions,
    }


def plot_charts_to_buffer(chart_data: Dict[str, List[Any]]) -> io.BytesIO:
    labels = chart_data["labels"]
    regs = chart_data["registrations"]
    earnings = chart_data["earnings"]
    click_conv = chart_data["click_conversions"]
    user_conv = chart_data["user_conversions"]
    
    # 3 subplots vertically stacked
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 15))
    
    # Plot 1: Registrations
    bars1 = ax1.bar(labels, regs, color="#3b82f6", width=0.4, alpha=0.85, edgecolor="#2563eb", linewidth=1.2)
    ax1.set_title("Регистрации (по дням)", fontsize=14, fontweight="bold", pad=10)
    ax1.grid(True, linestyle="--", alpha=0.5)
    
    # Plot 2: Earnings
    bars2 = ax2.bar(labels, earnings, color="#10b981", width=0.4, alpha=0.85, edgecolor="#059669", linewidth=1.2)
    ax2.set_title("Выручка (по дням, RUB)", fontsize=14, fontweight="bold", pad=10)
    ax2.grid(True, linestyle="--", alpha=0.5)
    
    # Plot 3: Conversions
    ax3.plot(labels, click_conv, marker="o", color="#f59e0b", linewidth=2.5, label="Клик -> Оплата")
    ax3.plot(labels, user_conv, marker="s", color="#8b5cf6", linewidth=2.5, label="Рег -> Оплата")
    ax3.set_title("Конверсия (по дням, %)", fontsize=14, fontweight="bold", pad=10)
    ax3.grid(True, linestyle="--", alpha=0.5)
    ax3.set_ylim(-5, 105)
    ax3.legend(loc="upper right", framealpha=0.9)
    
    show_labels = len(labels) <= 15
    
    # Styling and Annotating plots
    for ax in [ax1, ax2, ax3]:
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#ddd')
        ax.spines['bottom'].set_color('#ddd')
        ax.tick_params(colors='#555', labelsize=10)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=30, ha='right')
        
    if show_labels:
        # Annotate Registrations
        for bar in bars1:
            height = bar.get_height()
            if height > 0:
                ax1.annotate(f"{height}",
                             xy=(bar.get_x() + bar.get_width() / 2, height),
                             xytext=(0, 3),
                             textcoords="offset points",
                             ha="center", va="bottom", fontsize=9, fontweight="bold", color="#1e3a8a")
                             
        # Annotate Earnings
        for bar in bars2:
            height = bar.get_height()
            if height > 0:
                ax2.annotate(f"{height:.0f}",
                             xy=(bar.get_x() + bar.get_width() / 2, height),
                             xytext=(0, 3),
                             textcoords="offset points",
                             ha="center", va="bottom", fontsize=9, fontweight="bold", color="#065f46")
                             
        # Annotate Conversions
        for i, val in enumerate(click_conv):
            if val > 0:
                ax3.annotate(f"{val:.1f}%", xy=(i, val), xytext=(0, 7), textcoords="offset points",
                             ha="center", va="bottom", fontsize=8, fontweight="bold", color="#d97706")
        for i, val in enumerate(user_conv):
            if val > 0:
                ax3.annotate(f"{val:.1f}%", xy=(i, val), xytext=(0, -14), textcoords="offset points",
                             ha="center", va="bottom", fontsize=8, fontweight="bold", color="#7c3aed")
                             
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    buf.seek(0)
    plt.close(fig)
    return buf


def parse_date_arg(arg_str: str) -> Optional[datetime]:
    arg_str = arg_str.lower().strip()
    
    # 1. YYYY-MM-DD
    try:
        dt = datetime.strptime(arg_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
        
    # 2. DD-MM-YYYY
    try:
        dt = datetime.strptime(arg_str, "%d-%m-%Y")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
        
    # 3. DD.MM.YYYY
    try:
        dt = datetime.strptime(arg_str, "%d.%m.%Y")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
        
    # 4. DD.MM (assume current year)
    try:
        dt = datetime.strptime(arg_str, "%d.%m")
        current_year = datetime.now(timezone.utc).year
        return dt.replace(year=current_year, tzinfo=timezone.utc)
    except ValueError:
        pass
        
    # 5. DD (number of days ago)
    if arg_str.isdigit():
        try:
            days_ago = int(arg_str)
            dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        except ValueError:
            pass

    # 6. Try matching month words (English & Russian)
    months_en = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    months_ru = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
    
    arg_clean = arg_str
    replacements = {
        "января": "янв", "февраля": "фев", "марта": "мар", "апреля": "апр", 
        "мая": "май", "июня": "июн", "июля": "июл", "августа": "авг", 
        "сентября": "сен", "октября": "окт", "ноября": "ноя", "декабря": "дек"
    }
    for k, v in replacements.items():
        if k in arg_clean:
            arg_clean = arg_clean.replace(k, v)
            
    match = re.match(r"(\d+)\s+([a-zа-я]+)", arg_clean)
    if match:
        day = int(match.group(1))
        month_word = match.group(2)
        month_idx = -1
        
        if month_word in months_en:
            month_idx = months_en.index(month_word) + 1
        elif month_word in months_ru or month_word.startswith("май"):
            if month_word.startswith("май"):
                month_idx = 5
            else:
                month_idx = months_ru.index(month_word) + 1
                
        if month_idx != -1:
            current_year = datetime.now(timezone.utc).year
            try:
                return datetime(current_year, month_idx, day, tzinfo=timezone.utc)
            except ValueError:
                pass

    return None


@router.message(Command("stats_chart", "chart"))
async def cmd_stats_chart(message: Message) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("Access denied.")
        return

    status_msg = await message.answer("📊 Собираю данные и формирую графики... Пожалуйста, подождите.")
    
    try:
        now = datetime.now(timezone.utc)
        start_time = None
        
        args = message.text.split(maxsplit=1)
        if len(args) > 1:
            start_time = parse_date_arg(args[1])
            
        if not start_time:
            # Default to 21 May 2026 as requested
            start_time = datetime(2026, 5, 21, tzinfo=timezone.utc)
            
        # Cap starting range to 60 days to prevent performance issues
        max_days = 60
        min_start_time = now - timedelta(days=max_days)
        if start_time < min_start_time:
            start_time = min_start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            warning_msg = f"⚠️ Заданный период слишком велик. График ограничен последними {max_days} днями."
        else:
            warning_msg = None

        db = init_firestore()
        # Query Firestore in a separate thread because the SDK is blocking
        raw_data = await asyncio.to_thread(fetch_raw_data, db, start_time)

        # Generate bins
        bins = generate_daily_bins(start_time, now)
        if not bins:
            await status_msg.edit_text("❌ Недостаточно данных для построения графика.")
            return

        # Calculate metrics for each bin
        chart_data = calculate_daily_chart_data(raw_data, bins)
        
        # Render chart in a separate thread because matplotlib plotting can be CPU intensive
        buf = await asyncio.to_thread(plot_charts_to_buffer, chart_data)
        
        # Build caption
        start_str = start_time.strftime("%d.%m.%Y")
        end_str = now.strftime("%d.%m.%Y")
        caption = f"📊 <b>Статистика с {start_str} по {end_str}</b>\n\n"
        if warning_msg:
            caption += warning_msg + "\n\n"
            
        # Add summary stats in the caption for easy reading
        total_regs = sum(chart_data["registrations"])
        total_revenue = sum(chart_data["earnings"])
        caption += (
            f"👤 Всего регистраций: <b>{total_regs}</b>\n"
            f"💵 Общая выручка: <b>{total_revenue:.2f} RUB</b>\n"
        )
        
        photo = BufferedInputFile(buf.getvalue(), filename="stats_chart.png")
        await message.answer_photo(photo, caption=caption, parse_mode="HTML")
        await status_msg.delete()

    except Exception as e:
        logger.exception("Failed to generate statistics chart")
        await status_msg.edit_text(f"❌ Не удалось построить график: {e}")

