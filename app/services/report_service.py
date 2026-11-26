from datetime import datetime, time, timedelta, timezone

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models.menu import MenuItem
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.refund import Refund, RefundStatus
from app.services.errors import OrderError

MAX_RANGE_DAYS = 366
DEFAULT_SALES_DAYS = 30
TOP_ITEMS_MAX = 50

# Orders that were paid at some point. Refunds reduce revenue but don't remove the order from these numbers.
PAID_STATUSES = (
    PaymentStatus.PAID,
    PaymentStatus.PARTIALLY_REFUNDED,
    PaymentStatus.REFUNDED,
)

# Items deleted from the menu keep their sales, grouped under this label.
REMOVED_CATEGORY_LABEL = "Removed from menu"


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def canteen_utc_offset_minutes():
    return int(current_app.config["CANTEEN_UTC_OFFSET_MINUTES"])


def canteen_tz():
    return timezone(timedelta(minutes=canteen_utc_offset_minutes()))


def _local_day(created_at, tz):
    return _as_utc(created_at).astimezone(tz).date().isoformat()


def _parse_date(raw, name):
    if raw is None:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise OrderError("INVALID_DATE", f"'{name}' must be a date in YYYY-MM-DD format.")


def _local_midnight_utc(day):
    """Midnight at the start of a canteen-local day, as naive UTC (how the database stores times)."""
    local = datetime.combine(day, time(0), tzinfo=canteen_tz())
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def date_bounds(args, default_days=None):
    """Return (start, end) as naive UTC. start is inclusive, end is exclusive. Either may be None (open).

    Dates are canteen-local calendar days, and 'to' is included in the range.
    """
    start_day = _parse_date(args.get("from"), "from")
    end_day = _parse_date(args.get("to"), "to")

    if start_day is None and end_day is None and default_days:
        end_day = datetime.now(canteen_tz()).date()
        start_day = end_day - timedelta(days=default_days - 1)

    if start_day and end_day:
        if start_day > end_day:
            raise OrderError("INVALID_DATE_RANGE", "'from' must be on or before 'to'.")
        if (end_day - start_day).days + 1 > MAX_RANGE_DAYS:
            raise OrderError(
                "INVALID_DATE_RANGE",
                f"A date range cannot be longer than {MAX_RANGE_DAYS} days.",
            )

    start = _local_midnight_utc(start_day) if start_day else None
    end = _local_midnight_utc(end_day + timedelta(days=1)) if end_day else None
    return start, end


def _in_range(query, column, start, end):
    if start is not None:
        query = query.filter(column >= start)
    if end is not None:
        query = query.filter(column < end)
    return query


def _paid_orders(start, end):
    return _in_range(
        Order.query.filter(Order.payment_status.in_(PAID_STATUSES)),
        Order.created_at,
        start,
        end,
    )


def _refunded_total(start, end):
    """Sum of processed refunds. A refund counts on the day of the order it belongs to."""
    query = (
        db.session.query(func.coalesce(func.sum(Refund.amount_paise), 0))
        .select_from(Refund)
        .join(Order, Order.id == Refund.order_id)
        .filter(Refund.status == RefundStatus.PROCESSED)
    )
    return int(_in_range(query, Order.created_at, start, end).scalar() or 0)


def _average_preparation_minutes(start, end):
    """Average minutes from 'preparing' to 'ready', for orders that went through both."""
    query = (
        db.session.query(
            OrderStatusHistory.order_id,
            OrderStatusHistory.new_status,
            OrderStatusHistory.changed_at,
        )
        .select_from(OrderStatusHistory)
        .join(Order, Order.id == OrderStatusHistory.order_id)
        .filter(OrderStatusHistory.new_status.in_([OrderStatus.PREPARING, OrderStatus.READY]))
    )
    query = _in_range(query, Order.created_at, start, end).order_by(
        OrderStatusHistory.changed_at,
        OrderStatusHistory.id,
    )

    first_seen = {}
    for order_id, new_status, changed_at in query.all():
        first_seen.setdefault(order_id, {}).setdefault(new_status, _as_utc(changed_at))

    durations = [
        (stamps[OrderStatus.READY] - stamps[OrderStatus.PREPARING]).total_seconds() / 60
        for stamps in first_seen.values()
        if OrderStatus.PREPARING in stamps and OrderStatus.READY in stamps
    ]
    if not durations:
        return None
    return round(sum(durations) / len(durations), 1)


def overview(start, end):
    orders = _in_range(Order.query, Order.created_at, start, end)
    total_orders = orders.count()
    cancelled_orders = orders.filter(Order.order_status == OrderStatus.CANCELLED).count()

    paid = _paid_orders(start, end)
    paid_orders = paid.count()
    gross_revenue = int(
        paid.with_entities(func.coalesce(func.sum(Order.total_paise), 0)).scalar() or 0
    )
    collected_paid_orders = paid.filter(Order.order_status == OrderStatus.COLLECTED).count()
    refunded = _refunded_total(start, end)

    return {
        "total_orders": total_orders,
        "paid_orders": paid_orders,
        "cancelled_orders": cancelled_orders,
        "gross_revenue_paise": gross_revenue,
        "refunded_paise": refunded,
        "net_revenue_paise": gross_revenue - refunded,
        "average_order_value_paise": gross_revenue // paid_orders if paid_orders else 0,
        "completion_rate_percent": (
            round(collected_paid_orders / paid_orders * 100, 1) if paid_orders else 0.0
        ),
        "average_preparation_minutes": _average_preparation_minutes(start, end),
    }


def sales_by_day(start, end):
    tz = canteen_tz()
    days = {}

    def entry_for(day):
        return days.setdefault(day, {"date": day, "orders": 0, "revenue_paise": 0, "refunded_paise": 0})

    for created_at, total in _paid_orders(start, end).with_entities(
        Order.created_at, Order.total_paise
    ).all():
        row = entry_for(_local_day(created_at, tz))
        row["orders"] += 1
        row["revenue_paise"] += total

    refund_query = (
        db.session.query(Order.created_at, Refund.amount_paise)
        .select_from(Refund)
        .join(Order, Order.id == Refund.order_id)
        .filter(Refund.status == RefundStatus.PROCESSED)
    )
    for created_at, amount in _in_range(refund_query, Order.created_at, start, end).all():
        entry_for(_local_day(created_at, tz))["refunded_paise"] += amount

    return [days[key] for key in sorted(days)]


def popular_items(start, end, limit):
    query = (
        db.session.query(
            OrderItem.menu_item_id,
            OrderItem.item_name_snapshot,
            func.sum(OrderItem.quantity),
            func.sum(OrderItem.line_total_paise),
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.payment_status.in_(PAID_STATUSES))
    )
    query = _in_range(query, Order.created_at, start, end)
    rows = (
        query.group_by(OrderItem.menu_item_id, OrderItem.item_name_snapshot)
        .order_by(func.sum(OrderItem.quantity).desc(), OrderItem.item_name_snapshot.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "menu_item_id": row[0],
            "item_name": row[1],
            "quantity": int(row[2]),
            "revenue_paise": int(row[3]),
        }
        for row in rows
    ]


def category_sales(start, end):
    # Outer join so items removed from the menu still count toward revenue.
    query = (
        db.session.query(
            MenuItem.category,
            func.sum(OrderItem.quantity),
            func.sum(OrderItem.line_total_paise),
        )
        .select_from(OrderItem)
        .outerjoin(MenuItem, MenuItem.id == OrderItem.menu_item_id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.payment_status.in_(PAID_STATUSES))
    )
    query = _in_range(query, Order.created_at, start, end)
    rows = (
        query.group_by(MenuItem.category)
        .order_by(func.sum(OrderItem.line_total_paise).desc())
        .all()
    )

    totals = {}
    for category, quantity, revenue in rows:
        label = category or REMOVED_CATEGORY_LABEL
        entry = totals.setdefault(label, {"category": label, "quantity": 0, "revenue_paise": 0})
        entry["quantity"] += int(quantity)
        entry["revenue_paise"] += int(revenue)

    return sorted(totals.values(), key=lambda row: row["revenue_paise"], reverse=True)


def peak_hours(start, end):
    """Paid orders per hour of the canteen's local day, 0 to 23."""
    tz = canteen_tz()
    counts = [0] * 24
    rows = _paid_orders(start, end).with_entities(Order.created_at).all()
    for (created_at,) in rows:
        counts[_as_utc(created_at).astimezone(tz).hour] += 1
    return [{"hour": hour, "orders": counts[hour]} for hour in range(24)]


def order_statistics(start, end):
    orders = _in_range(Order.query, Order.created_at, start, end)

    by_order_status = {
        status: count
        for status, count in orders.with_entities(Order.order_status, func.count(Order.id))
        .group_by(Order.order_status)
        .all()
    }
    by_payment_status = {
        status: count
        for status, count in orders.with_entities(Order.payment_status, func.count(Order.id))
        .group_by(Order.payment_status)
        .all()
    }
    return {
        "total": orders.count(),
        "by_order_status": by_order_status,
        "by_payment_status": by_payment_status,
    }


# Public report-service names used by the API routes.
report_overview = overview
report_sales = sales_by_day
report_popular_items = popular_items
report_categories = category_sales
report_peak_hours = peak_hours
report_orders = order_statistics
