from tests.session_helpers import issue_test_session
import pytest

from app.extensions import db
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.services.order_service import create_order


def make_user(email, role=UserRole.STUDENT, name="Test User"):
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


def order_for(user, menu, quantity=1):
    order, _ = create_order(
        user.id,
        [{"menu_item_id": menu["samosa"].id, "quantity": quantity}],
    )
    return order


@pytest.fixture
def other_student(app):
    return make_user("other@test.com", name="Other Student")


@pytest.fixture
def admin_client(app):
    admin = make_user("admin@test.com", role=UserRole.ADMIN, name="Admin")
    return login_as(app.test_client(), admin)


# ---------- Student: list ----------

def test_list_returns_only_own_orders(client, student, other_student, menu):
    order_for(student, menu)
    order_for(student, menu)
    order_for(other_student, menu)

    response = client.get("/api/orders")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["pagination"]["total"] == 2
    assert len(data["orders"]) == 2


def test_list_is_empty_for_new_student(client, menu):
    response = client.get("/api/orders")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["orders"] == []
    assert data["pagination"]["total"] == 0


def test_list_is_paginated(client, student, menu):
    for _ in range(3):
        order_for(student, menu)

    first = client.get("/api/orders?per_page=2").get_json()["data"]
    assert len(first["orders"]) == 2
    assert first["pagination"]["total"] == 3
    assert first["pagination"]["pages"] == 2
    assert first["pagination"]["has_next"] is True

    second = client.get("/api/orders?per_page=2&page=2").get_json()["data"]
    assert len(second["orders"]) == 1
    assert second["pagination"]["has_next"] is False


def test_list_orders_newest_first(client, student, menu):
    first = order_for(student, menu)
    second = order_for(student, menu)

    orders = client.get("/api/orders").get_json()["data"]["orders"]

    assert orders[0]["order_number"] == second.order_number
    assert orders[1]["order_number"] == first.order_number


@pytest.mark.parametrize("query", [
    "page=0",
    "page=abc",
    "page=-1",
    "per_page=0",
    "per_page=51",
    "per_page=abc",
])
def test_list_rejects_bad_pagination(client, query):
    response = client.get(f"/api/orders?{query}")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_PAGINATION"


def test_list_requires_login(anon_client):
    response = anon_client.get("/api/orders")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTH_REQUIRED"


# ---------- Student: detail ----------

def test_get_own_order(client, student, menu):
    order = order_for(student, menu, quantity=2)

    response = client.get(f"/api/orders/{order.id}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["order_number"] == order.order_number
    assert data["total_paise"] == 3000
    assert data["items"][0]["item_name"] == "Samosa"
    assert "tracking_token" not in data


def test_cannot_view_another_students_order(client, other_student, menu):
    order = order_for(other_student, menu)

    response = client.get(f"/api/orders/{order.id}")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "ORDER_NOT_FOUND"


def test_missing_order_returns_404(client):
    response = client.get("/api/orders/99999")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "ORDER_NOT_FOUND"


# ---------- Student: tracking ----------

def test_tracking_returns_status_only(client, student, menu):
    order = order_for(student, menu)

    response = client.get(f"/api/orders/{order.id}/tracking")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["order_status"] == OrderStatus.PENDING_PAYMENT
    assert data["payment_status"] == "pending"
    assert "items" not in data
    assert "total_paise" not in data
    assert "tracking_token" not in data


def test_cannot_track_another_students_order(client, other_student, menu):
    order = order_for(other_student, menu)

    response = client.get(f"/api/orders/{order.id}/tracking")

    assert response.status_code == 404


# ---------- Admin ----------

def test_student_cannot_use_admin_list(client, menu):
    response = client.get("/api/admin/orders")

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_student_cannot_use_admin_detail(client, other_student, menu):
    order = order_for(other_student, menu)

    response = client.get(f"/api/admin/orders/{order.id}")

    assert response.status_code == 403


def test_admin_list_shows_all_orders_with_student(admin_client, student, other_student, menu):
    order_for(student, menu)
    order_for(other_student, menu)

    response = admin_client.get("/api/admin/orders")

    assert response.status_code == 200
    orders = response.get_json()["data"]["orders"]
    assert len(orders) == 2
    emails = {order["student"]["email"] for order in orders}
    assert emails == {"student@test.com", "other@test.com"}


def test_admin_can_view_any_order(admin_client, other_student, menu):
    order = order_for(other_student, menu)

    response = admin_client.get(f"/api/admin/orders/{order.id}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["order_number"] == order.order_number
    assert data["student"]["email"] == "other@test.com"


def test_admin_missing_order_returns_404(admin_client):
    response = admin_client.get("/api/admin/orders/99999")

    assert response.status_code == 404


def test_admin_filters_by_order_status(admin_client, student, menu):
    received = order_for(student, menu)
    order_for(student, menu)

    stored = db.session.get(Order, received.id)
    stored.order_status = OrderStatus.RECEIVED
    db.session.commit()

    received_list = admin_client.get("/api/admin/orders?order_status=received").get_json()["data"]
    pending_list = admin_client.get("/api/admin/orders?order_status=pending_payment").get_json()["data"]

    assert received_list["pagination"]["total"] == 1
    assert received_list["orders"][0]["order_number"] == received.order_number
    assert pending_list["pagination"]["total"] == 1


def test_admin_rejects_unknown_filter(admin_client):
    response = admin_client.get("/api/admin/orders?order_status=bogus")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_FILTER"
