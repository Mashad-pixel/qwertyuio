from tests.session_helpers import issue_test_session
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models.menu import MenuItem
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.user import User, UserRole
from app.services.order_service import create_order
from app.services.payment_service import _confirm_captured_payment, create_payment_order


def make_user(email, role, name="Test User"):
    user = User(name=name, email=email, role=role, is_active=True)
    user.set_password("StrongPass123!")
    db.session.add(user)
    db.session.commit()
    return user


def login_as(test_client, user):
    with test_client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["sid"] = issue_test_session(user)
    return test_client


def pay(student, menu_key, menu, quantity):
    order, _ = create_order(student.id, [{"menu_item_id": menu[menu_key].id, "quantity": quantity}])
    fake = MagicMock()
    fake.order.create.return_value = {"id": f"order_{uuid.uuid4().hex[:12]}"}
    with patch("app.services.payment_service.get_razorpay_client", return_value=fake):
        payment, _ = create_payment_order(order.id, student.id)
    _confirm_captured_payment(
        payment,
        provider_payment_id=f"pay_{uuid.uuid4().hex[:12]}",
        amount_paise=order.total_paise,
        currency="INR",
    )
    return db.session.get(Order, order.id)


def set_status(order_id, status):
    stored = db.session.get(Order, order_id)
    stored.order_status = status
    db.session.commit()


@pytest.fixture
def admin_client(app):
    admin = make_user("admin@test.com", UserRole.ADMIN, name="Admin")
    return login_as(app.test_client(), admin)


@pytest.fixture
def sample_data(app, student, menu):
    """Two paid orders: 2 samosas (3000) and 1 tea (1000). Returns the two orders."""
    samosa_order = pay(student, "samosa", menu, 2)
    tea_order = pay(student, "tea", menu, 1)
    return samosa_order, tea_order


# ---------- Overview ----------

def test_overview_counts_and_revenue(admin_client, sample_data):
    response = admin_client.get("/api/admin/reports/overview")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["total_orders"] == 2
    assert data["paid_orders"] == 2
    assert data["cancelled_orders"] == 0
    assert data["gross_revenue_paise"] == 4000
    assert data["refunded_paise"] == 0
    assert data["net_revenue_paise"] == 4000
    assert data["average_order_value_paise"] == 2000
    assert data["completion_rate_percent"] == 0.0


def test_overview_completion_rate(admin_client, sample_data):
    samosa_order, _ = sample_data
    set_status(samosa_order.id, OrderStatus.COLLECTED)

    data = admin_client.get("/api/admin/reports/overview").get_json()["data"]

    assert data["completion_rate_percent"] == 50.0


def test_unpaid_and_cancelled_orders_are_not_revenue(admin_client, student, menu, sample_data):
    create_order(student.id, [{"menu_item_id": menu["samosa"].id, "quantity": 1}])  # unpaid
    cancelled, _ = create_order(student.id, [{"menu_item_id": menu["samosa"].id, "quantity": 1}])
    set_status(cancelled.id, OrderStatus.CANCELLED)

    data = admin_client.get("/api/admin/reports/overview").get_json()["data"]

    assert data["total_orders"] == 4
    assert data["paid_orders"] == 2
    assert data["cancelled_orders"] == 1
    assert data["gross_revenue_paise"] == 4000


def test_refunds_reduce_net_revenue(app, admin_client, student, menu, sample_data):
    from app.models.refund import Refund, RefundStatus
    from app.models.payment import Payment

    _, tea_order = sample_data
    payment = Payment.query.filter_by(order_id=tea_order.id).one()
    db.session.add(Refund(
        payment_id=payment.id,
        order_id=tea_order.id,
        provider_refund_id=f"rfnd_{uuid.uuid4().hex[:10]}",
        amount_paise=1000,
        status=RefundStatus.PROCESSED,
    ))
    db.session.commit()

    data = admin_client.get("/api/admin/reports/overview").get_json()["data"]

    assert data["refunded_paise"] == 1000
    assert data["net_revenue_paise"] == 3000
    assert data["gross_revenue_paise"] == 4000


def test_preparation_time_is_reported(app, admin_client, student, menu, sample_data):
    from app.models.order_status_history import OrderStatusHistory
    from datetime import datetime, timedelta, timezone

    samosa_order, _ = sample_data
    now = datetime.now(timezone.utc)
    db.session.add(OrderStatusHistory(
        order_id=samosa_order.id, previous_status="received", new_status="preparing",
        changed_by=None, changed_at=now - timedelta(minutes=8),
    ))
    db.session.add(OrderStatusHistory(
        order_id=samosa_order.id, previous_status="preparing", new_status="ready",
        changed_by=None, changed_at=now,
    ))
    db.session.commit()

    data = admin_client.get("/api/admin/reports/overview").get_json()["data"]

    assert data["average_preparation_minutes"] == pytest.approx(8.0, abs=0.2)


def test_empty_range_returns_zeros(admin_client, sample_data):
    data = admin_client.get("/api/admin/reports/overview?from=2001-01-01&to=2001-01-31").get_json()["data"]

    assert data["total_orders"] == 0
    assert data["gross_revenue_paise"] == 0
    assert data["average_order_value_paise"] == 0
    assert data["completion_rate_percent"] == 0.0
    assert data["average_preparation_minutes"] is None


# ---------- Sales by day ----------

def test_sales_by_day_totals_match_overview(admin_client, sample_data):
    response = admin_client.get("/api/admin/reports/sales")

    assert response.status_code == 200
    days = response.get_json()["data"]["days"]
    assert sum(day["revenue_paise"] for day in days) == 4000
    assert sum(day["orders"] for day in days) == 2
    assert days == sorted(days, key=lambda day: day["date"])


def test_sales_defaults_to_last_30_days_and_includes_refunds(app, admin_client, sample_data):
    from app.models.refund import Refund, RefundStatus
    from app.models.payment import Payment

    _, tea_order = sample_data
    payment = Payment.query.filter_by(order_id=tea_order.id).one()
    db.session.add(Refund(
        payment_id=payment.id, order_id=tea_order.id,
        provider_refund_id=f"rfnd_{uuid.uuid4().hex[:10]}",
        amount_paise=500, status=RefundStatus.PROCESSED,
    ))
    db.session.commit()

    days = admin_client.get("/api/admin/reports/sales").get_json()["data"]["days"]

    assert sum(day["refunded_paise"] for day in days) == 500


# ---------- Popular items and categories ----------

def test_popular_items_ordered_by_quantity(admin_client, sample_data):
    response = admin_client.get("/api/admin/reports/popular-items")

    assert response.status_code == 200
    items = response.get_json()["data"]["items"]
    assert items[0]["item_name"] == "Samosa"
    assert items[0]["quantity"] == 2
    assert items[0]["revenue_paise"] == 3000
    assert items[1]["item_name"] == "Tea"


def test_popular_items_limit(admin_client, sample_data):
    items = admin_client.get("/api/admin/reports/popular-items?limit=1").get_json()["data"]["items"]

    assert len(items) == 1


@pytest.mark.parametrize("query", ["limit=0", "limit=51", "limit=abc"])
def test_popular_items_rejects_bad_limit(admin_client, query):
    response = admin_client.get(f"/api/admin/reports/popular-items?{query}")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_PAGINATION"


def test_category_sales(admin_client, sample_data):
    categories = admin_client.get("/api/admin/reports/categories").get_json()["data"]["categories"]

    by_name = {row["category"]: row for row in categories}
    assert by_name["Snacks"]["revenue_paise"] == 3000
    assert by_name["Snacks"]["quantity"] == 2
    assert by_name["Drinks"]["revenue_paise"] == 1000


def test_removed_menu_item_keeps_category_revenue(admin_client, student, menu):
    item = menu["samosa"]
    order, _ = create_order(student.id, [{"menu_item_id": item.id, "quantity": 1}])
    fake = MagicMock()
    fake.order.create.return_value = {"id": f"order_{uuid.uuid4().hex[:12]}"}
    with patch("app.services.payment_service.get_razorpay_client", return_value=fake):
        payment, _ = create_payment_order(order.id, student.id)
    _confirm_captured_payment(
        payment, provider_payment_id=f"pay_{uuid.uuid4().hex[:12]}",
        amount_paise=order.total_paise, currency="INR",
    )
    db.session.delete(item)
    db.session.commit()

    rows = admin_client.get("/api/admin/reports/categories").get_json()["data"]["categories"]
    assert rows[0]["category"] == "Removed from menu"
    assert rows[0]["revenue_paise"] == 1500


def test_peak_hours_has_all_24_hours_and_counts_orders(admin_client, sample_data):
    response = admin_client.get("/api/admin/reports/peak-hours")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert [row["hour"] for row in data["hours"]] == list(range(24))
    assert sum(row["orders"] for row in data["hours"]) == 2
    assert data["timezone_offset_minutes"] == 330


def test_order_statistics(admin_client, student, menu, sample_data):
    create_order(student.id, [{"menu_item_id": menu["tea"].id, "quantity": 1}])

    data = admin_client.get("/api/admin/reports/orders").get_json()["data"]

    assert data["total"] == 3
    assert data["by_payment_status"]["paid"] == 2
    assert data["by_payment_status"]["pending"] == 1
    assert data["by_order_status"]["received"] == 2


# ---------- Dates and roles ----------

@pytest.mark.parametrize("query", [
    "from=2026-13-01",
    "from=not-a-date",
    "to=2026-02-30",
])
def test_invalid_dates_rejected(admin_client, query):
    response = admin_client.get(f"/api/admin/reports/overview?{query}")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_DATE"


def test_start_after_end_rejected(admin_client):
    response = admin_client.get("/api/admin/reports/overview?from=2026-02-10&to=2026-02-01")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_range_longer_than_a_year_rejected(admin_client):
    response = admin_client.get("/api/admin/reports/sales?from=2024-01-01&to=2026-01-01")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_DATE_RANGE"


@pytest.mark.parametrize("path", [
    "/api/admin/reports/overview",
    "/api/admin/reports/sales",
    "/api/admin/reports/popular-items",
    "/api/admin/reports/categories",
    "/api/admin/reports/peak-hours",
    "/api/admin/reports/orders",
])
def test_reports_are_admin_only(client, path):
    response = client.get(path)

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_reports_require_login(anon_client):
    response = anon_client.get("/api/admin/reports/overview")

    assert response.status_code == 401
