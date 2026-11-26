from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.datastructures import MultiDict

from app.extensions import db
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.user import UserRole
from app.services.errors import OrderError
from app.services.order_query_service import MAX_PAGE, MAX_PER_PAGE, parse_pagination
from tests.test_reports import login_as, make_user


def make_order(student_id, number, created_at=None):
    """Insert an unpaid order directly. Query tests only need rows, not payment flow."""
    order = Order(
        order_number=f"TQ{number:08d}",
        student_id=student_id,
        subtotal_paise=1000,
        discount_paise=0,
        tax_paise=0,
        total_paise=1000,
        payment_status=PaymentStatus.PENDING,
        order_status=OrderStatus.PENDING_PAYMENT,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.session.add(order)
    db.session.commit()
    return order


# ---------- parse_pagination (unit) ----------

def test_defaults_when_no_parameters_given():
    assert parse_pagination(MultiDict()) == (1, 10)


@pytest.mark.parametrize("query, expected", [
    ({"page": "1", "per_page": "1"}, (1, 1)),
    ({"page": str(MAX_PAGE), "per_page": str(MAX_PER_PAGE)}, (MAX_PAGE, MAX_PER_PAGE)),
    ({"page": " 3 ", "per_page": " 7 "}, (3, 7)),
])
def test_accepts_boundary_values(query, expected):
    assert parse_pagination(MultiDict(query)) == expected


@pytest.mark.parametrize("query", [
    {"page": "0"},
    {"page": "-1"},
    {"page": "abc"},
    {"page": ""},
    {"page": "1.5"},
    {"per_page": "0"},
    {"per_page": str(MAX_PER_PAGE + 1)},
    {"page": str(MAX_PAGE + 1)},
    {"page": "9" * 50},
])
def test_rejects_out_of_range_values(query):
    with pytest.raises(OrderError) as excinfo:
        parse_pagination(MultiDict(query))

    assert excinfo.value.code == "INVALID_PAGINATION"
    assert excinfo.value.status == 400


# ---------- HTTP behaviour ----------

def test_per_page_one_walks_every_order_exactly_once(client, student):
    for number in range(3):
        make_order(student.id, number)

    seen = []
    for page in (1, 2, 3):
        data = client.get(f"/api/orders?page={page}&per_page=1").get_json()["data"]
        seen.extend(order["order_number"] for order in data["orders"])

    assert len(seen) == 3
    assert len(set(seen)) == 3


def test_last_page_has_no_next_and_page_past_end_is_empty(client, student):
    for number in range(3):
        make_order(student.id, number)

    last = client.get("/api/orders?page=2&per_page=2").get_json()["data"]
    assert len(last["orders"]) == 1
    assert last["pagination"]["has_next"] is False
    assert last["pagination"]["has_prev"] is True
    assert last["pagination"]["pages"] == 2
    assert last["pagination"]["total"] == 3

    beyond = client.get("/api/orders?page=50&per_page=2").get_json()["data"]
    assert beyond["orders"] == []
    assert beyond["pagination"]["has_next"] is False


def test_empty_history_reports_zero_pages(client):
    data = client.get("/api/orders").get_json()["data"]

    assert data["orders"] == []
    assert data["pagination"]["total"] == 0
    assert data["pagination"]["has_next"] is False


def test_orders_with_identical_timestamps_are_ordered_by_id(client, student):
    same_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    first = make_order(student.id, 1, created_at=same_time)
    second = make_order(student.id, 2, created_at=same_time)

    orders = client.get("/api/orders?per_page=50").get_json()["data"]["orders"]

    assert [order["id"] for order in orders] == [second.id, first.id]


def test_huge_page_number_is_rejected_not_a_server_error(client, student):
    """Regression: page=10**20 overflowed SQLite's integer range and returned 500."""
    response = client.get(f"/api/orders?page={10**20}")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_PAGINATION"


def test_page_at_the_limit_is_served(client, student):
    response = client.get(f"/api/orders?page={MAX_PAGE}")

    assert response.status_code == 200
    assert response.get_json()["data"]["orders"] == []


def test_admin_list_applies_the_same_bounds(app, student):
    admin = make_user("admin-query@test.com", UserRole.ADMIN, name="Admin")
    admin_client = login_as(app.test_client(), admin)

    assert admin_client.get(f"/api/admin/orders?page={10**20}").status_code == 400
    assert admin_client.get("/api/admin/orders?per_page=51").status_code == 400
    assert admin_client.get("/api/admin/orders?per_page=50").status_code == 200
