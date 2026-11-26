"""Report date windows: a canteen day includes every order placed on it, including late evening."""
from datetime import datetime, timezone

import pytest

from app.extensions import db
from app.models.order import Order, PaymentStatus
from app.models.user import User, UserRole
from app.services.order_service import create_order
from tests.session_helpers import issue_test_session


@pytest.fixture
def admin_client(app):
    admin = User(name="Admin", email="admin@test.com", role=UserRole.ADMIN, is_active=True)
    admin.set_password("StrongPass123!")
    db.session.add(admin)
    db.session.commit()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True
        sess["sid"] = issue_test_session(admin, mfa_verified=True)
    return client


def order_at(student, menu, created_utc):
    order, _ = create_order(student.id, [{"menu_item_id": menu["tea"].id, "quantity": 1}])
    stored = db.session.get(Order, order.id)
    stored.created_at = created_utc
    db.session.commit()
    return stored


def test_an_order_placed_during_the_last_day_is_counted(admin_client, student, menu):
    # 10:00 on 2026-02-10 in India (UTC+05:30) is 04:30 UTC on the same date.
    # The old code compared against midnight UTC, so a range ending that day dropped it.
    order_at(student, menu, datetime(2026, 2, 10, 4, 30, tzinfo=timezone.utc))

    data = admin_client.get("/api/admin/reports/overview?from=2026-02-10&to=2026-02-10").get_json()["data"]
    assert data["total_orders"] == 1


def test_an_order_from_the_evening_before_is_not_counted_for_a_one_day_range(admin_client, student, menu):
    # 23:30 on 2026-02-09 in India is 18:00 UTC on 2026-02-09, outside the 2026-02-10 range.
    order_at(student, menu, datetime(2026, 2, 9, 18, 0, tzinfo=timezone.utc))

    data = admin_client.get("/api/admin/reports/overview?from=2026-02-10&to=2026-02-10").get_json()["data"]
    assert data["total_orders"] == 0


def test_the_end_of_the_canteen_day_is_included(admin_client, student, menu):
    # 23:59 on 2026-02-10 in India is 18:29 UTC on the same date. It belongs to that day.
    order_at(student, menu, datetime(2026, 2, 10, 18, 29, tzinfo=timezone.utc))

    data = admin_client.get("/api/admin/reports/overview?from=2026-02-10&to=2026-02-10").get_json()["data"]
    assert data["total_orders"] == 1


def test_peak_hours_use_the_same_window(admin_client, student, menu):
    # Peak hours count paid orders only, so this order is marked paid first.
    paid = order_at(student, menu, datetime(2026, 2, 10, 4, 30, tzinfo=timezone.utc))
    paid.payment_status = PaymentStatus.PAID
    db.session.commit()
    data = admin_client.get("/api/admin/reports/peak-hours?from=2026-02-10&to=2026-02-10").get_json()["data"]
    assert data["timezone_offset_minutes"] == 330
    assert sum(hour["orders"] for hour in data["hours"]) == 1
