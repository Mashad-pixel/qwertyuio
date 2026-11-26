"""Scheduled expiry of unpaid orders: correctness, batching, monitoring and the CLI.

Creating any order runs the lazy sweep, so these tests create every order first and only
then backdate them. Otherwise the first order would be expired by the second one's request.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models.menu import MenuItem
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.order_status_history import OrderStatusHistory
from app.models.stock_reservation import ReservationStatus, StockReservation
from app.services import order_service
from app.services.order_service import create_order, expire_unpaid_orders, expiry_status
from tests.test_reports import pay


def create_unpaid(student, menu, key="tea", count=1, quantity=1):
    ids = []
    for _ in range(count):
        order, _ = create_order(student.id, [{"menu_item_id": menu[key].id, "quantity": quantity}])
        ids.append(order.id)
    return ids


def backdate(order_id, minutes_ago):
    stored = db.session.get(Order, order_id)
    stored.created_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    db.session.commit()


def status_of(order_id):
    db.session.expire_all()
    return db.session.get(Order, order_id).order_status


def reserved_of(menu_item_id):
    db.session.expire_all()
    return db.session.get(MenuItem, menu_item_id).reserved_quantity


# ---------- Which orders are expired ----------

def test_only_overdue_unpaid_orders_are_expired(student, menu):
    overdue = create_unpaid(student, menu, count=2)
    recent = create_unpaid(student, menu, count=1)
    paid_order = pay(student, "tea", menu, 1)
    for order_id in overdue:
        backdate(order_id, 30)
    backdate(paid_order.id, 600)  # very old, but paid: must never be expired

    expired = expire_unpaid_orders()

    assert expired == 2
    assert [status_of(i) for i in overdue] == [OrderStatus.CANCELLED, OrderStatus.CANCELLED]
    assert status_of(recent[0]) == OrderStatus.PENDING_PAYMENT
    assert status_of(paid_order.id) == OrderStatus.RECEIVED


def test_expiry_releases_held_stock_and_records_a_system_history_entry(student, menu):
    (order_id,) = create_unpaid(student, menu, key="paneer_roll", quantity=2)
    assert reserved_of(menu["paneer_roll"].id) == 2
    backdate(order_id, 30)

    expire_unpaid_orders()

    assert reserved_of(menu["paneer_roll"].id) == 0
    reservation = StockReservation.query.filter_by(order_id=order_id).one()
    assert reservation.status == ReservationStatus.RELEASED
    stored = db.session.get(Order, order_id)
    assert stored.payment_status == PaymentStatus.FAILED
    entry = OrderStatusHistory.query.filter_by(order_id=order_id, new_status=OrderStatus.CANCELLED).one()
    assert entry.changed_by is None  # system change, not a staff member
    assert entry.notes == "Payment not completed in time"


def test_sweep_is_idempotent(student, menu):
    ids = create_unpaid(student, menu, count=3)
    for order_id in ids:
        backdate(order_id, 30)

    assert expire_unpaid_orders() == 3
    assert expire_unpaid_orders() == 0


# ---------- Window boundary ----------

def test_order_exactly_at_the_window_edge_is_overdue(app, student, menu):
    (order_id,) = create_unpaid(student, menu)
    window = app.config["ORDER_PAYMENT_EXPIRY_MINUTES"]
    now = datetime(2026, 11, 30, 12, 0, tzinfo=timezone.utc)
    stored = db.session.get(Order, order_id)
    stored.created_at = now - timedelta(minutes=window)
    db.session.commit()

    assert expiry_status(now=now)["overdue_orders"] == 1


def test_order_one_second_inside_the_window_is_not_overdue(app, student, menu):
    (order_id,) = create_unpaid(student, menu)
    window = app.config["ORDER_PAYMENT_EXPIRY_MINUTES"]
    now = datetime(2026, 11, 30, 12, 0, tzinfo=timezone.utc)
    stored = db.session.get(Order, order_id)
    stored.created_at = now - timedelta(minutes=window) + timedelta(seconds=1)
    db.session.commit()

    assert expiry_status(now=now)["overdue_orders"] == 0


# ---------- Batching and per-batch atomicity ----------

def test_large_backlog_is_expired_in_batches(student, menu):
    ids = create_unpaid(student, menu, count=5)
    for order_id in ids:
        backdate(order_id, 30)

    assert expire_unpaid_orders(batch_size=2) == 5
    assert all(status_of(i) == OrderStatus.CANCELLED for i in ids)


def test_failure_rolls_back_only_the_batch_in_progress(student, menu):
    ids = create_unpaid(student, menu, count=4)
    for order_id in ids:
        backdate(order_id, 30)
    # Batches of two: the first batch commits, the second fails on its second order.
    failing_id = ids[3]
    real_expire = order_service.expire_order

    def flaky_expire(order, now=None):
        if order.id == failing_id:
            raise RuntimeError("simulated database failure")
        return real_expire(order, now)

    with patch.object(order_service, "expire_order", side_effect=flaky_expire):
        with pytest.raises(RuntimeError):
            expire_unpaid_orders(batch_size=2)

    assert [status_of(i) for i in ids[:2]] == [OrderStatus.CANCELLED, OrderStatus.CANCELLED]
    assert [status_of(i) for i in ids[2:]] == [OrderStatus.PENDING_PAYMENT, OrderStatus.PENDING_PAYMENT]

    # The next sweep finishes the job.
    assert expire_unpaid_orders(batch_size=2) == 2


# ---------- Monitoring ----------

def test_status_is_clean_when_nothing_is_overdue(app, student, menu):
    create_unpaid(student, menu, count=2)

    status = expiry_status()

    assert status["overdue_orders"] == 0
    assert status["oldest_overdue_minutes"] is None
    assert status["stalled"] is False


def test_recently_overdue_orders_are_not_yet_a_stall(app, student, menu):
    window = app.config["ORDER_PAYMENT_EXPIRY_MINUTES"]
    alert = app.config["ORDER_EXPIRY_ALERT_MINUTES"]
    (order_id,) = create_unpaid(student, menu)
    now = datetime(2026, 11, 30, 12, 0, tzinfo=timezone.utc)
    stored = db.session.get(Order, order_id)
    stored.created_at = now - timedelta(minutes=window + 2)
    db.session.commit()

    status = expiry_status(now=now)

    assert status["overdue_orders"] == 1
    assert status["oldest_overdue_minutes"] == pytest.approx(2.0)
    assert status["stalled"] is (2.0 > alert)


def test_orders_overdue_beyond_the_alert_threshold_mark_a_stall(app, student, menu):
    window = app.config["ORDER_PAYMENT_EXPIRY_MINUTES"]
    alert = app.config["ORDER_EXPIRY_ALERT_MINUTES"]
    (order_id,) = create_unpaid(student, menu)
    now = datetime(2026, 11, 30, 12, 0, tzinfo=timezone.utc)
    stored = db.session.get(Order, order_id)
    stored.created_at = now - timedelta(minutes=window + alert + 1)
    db.session.commit()

    status = expiry_status(now=now)

    assert status["stalled"] is True
    assert status["oldest_overdue_minutes"] == pytest.approx(alert + 1)


def test_status_check_never_changes_orders(app, student, menu):
    (order_id,) = create_unpaid(student, menu)
    backdate(order_id, 120)

    expiry_status()

    assert status_of(order_id) == OrderStatus.PENDING_PAYMENT


# ---------- CLI ----------

def test_cli_check_exits_zero_when_healthy(app, student, menu):
    create_unpaid(student, menu)

    result = app.test_cli_runner().invoke(args=["expire-orders", "--check"])

    assert result.exit_code == 0
    assert "Overdue unpaid orders: 0" in result.output


def test_cli_check_exits_one_when_the_sweep_is_stalled(app, student, menu):
    (order_id,) = create_unpaid(student, menu)
    backdate(order_id, app.config["ORDER_PAYMENT_EXPIRY_MINUTES"] + 60)

    result = app.test_cli_runner().invoke(args=["expire-orders", "--check"])

    assert result.exit_code == 1
    assert "STALLED" in result.output
    assert status_of(order_id) == OrderStatus.PENDING_PAYMENT  # check must not expire anything


def test_cli_sweep_reports_how_many_it_expired(app, student, menu):
    ids = create_unpaid(student, menu, count=2)
    for order_id in ids:
        backdate(order_id, 30)

    result = app.test_cli_runner().invoke(args=["expire-orders", "--batch-size", "1"])

    assert result.exit_code == 0
    assert "Expired 2 unpaid order(s)." in result.output


@pytest.mark.parametrize("bad", ["0", "1001", "abc"])
def test_cli_rejects_invalid_batch_size(app, bad):
    result = app.test_cli_runner().invoke(args=["expire-orders", "--batch-size", bad])

    assert result.exit_code == 2
