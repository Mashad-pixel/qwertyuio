from tests.session_helpers import issue_test_session
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.order_status_history import OrderStatusHistory
from app.models.user import User, UserRole
from app.services.order_service import create_order
from app.services.payment_service import _confirm_captured_payment, create_payment_order


# ---------- Helpers ----------

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


def make_order(user, menu, quantity=1):
    order, _ = create_order(
        user.id,
        [{"menu_item_id": menu["samosa"].id, "quantity": quantity}],
    )
    return order


def pay_order(order):
    """Run the real payment path with a mocked Razorpay client, so the order becomes paid."""
    provider_order_id = f"order_{uuid.uuid4().hex[:12]}"
    provider_payment_id = f"pay_{uuid.uuid4().hex[:12]}"

    fake_razorpay = MagicMock()
    fake_razorpay.order.create.return_value = {"id": provider_order_id}

    with patch("app.services.payment_service.get_razorpay_client", return_value=fake_razorpay):
        payment, _ = create_payment_order(order.id, order.student_id)

    _confirm_captured_payment(
        provider_order_id=payment.provider_order_id,
        provider_payment_id=provider_payment_id,
        amount_paise=order.total_paise,
        currency="INR",
    )
    return payment


def reload(model, pk):
    db.session.expire_all()
    return db.session.get(model, pk)


def set_status(order_id, status):
    """Set an order's status directly. Used only to set up states the kitchen can't reach."""
    stored = db.session.get(Order, order_id)
    stored.order_status = status
    db.session.commit()


def patch_status(test_client, order_id, status):
    return test_client.patch(
        f"/api/kitchen/orders/{order_id}/status",
        json={"status": status},
    )


@pytest.fixture
def kitchen_client(app):
    kitchen = make_user("kitchen@test.com", UserRole.KITCHEN, name="Kitchen Staff")
    return login_as(app.test_client(), kitchen), kitchen


@pytest.fixture
def admin_client(app):
    admin = make_user("admin@test.com", UserRole.ADMIN, name="Admin")
    return login_as(app.test_client(), admin), admin


# ---------- Queue ----------

def test_queue_shows_only_paid_orders(kitchen_client, client, student, menu):
    kitchen, _ = kitchen_client
    paid = make_order(student, menu)
    pay_order(paid)
    make_order(student, menu)  # unpaid

    response = kitchen.get("/api/kitchen/orders")

    assert response.status_code == 200
    queue = response.get_json()["data"]["queue"]
    received_ids = [order["id"] for order in queue["received"]]
    assert received_ids == [paid.id]
    assert queue["preparing"] == []
    assert queue["ready"] == []


def test_queue_has_no_student_contact_details(kitchen_client, student, menu):
    kitchen, _ = kitchen_client
    pay_order(make_order(student, menu))

    order = kitchen.get("/api/kitchen/orders").get_json()["data"]["queue"]["received"][0]

    assert "student" not in order
    assert "email" not in str(order)


def test_queue_is_oldest_first(kitchen_client, student, menu):
    kitchen, _ = kitchen_client
    first = make_order(student, menu)
    second = make_order(student, menu)
    pay_order(first)
    pay_order(second)

    received = kitchen.get("/api/kitchen/orders").get_json()["data"]["queue"]["received"]

    assert [order["id"] for order in received] == [first.id, second.id]


def test_queue_excludes_collected_and_cancelled(kitchen_client, student, menu):
    kitchen, _ = kitchen_client
    collected = make_order(student, menu)
    cancelled = make_order(student, menu)
    pay_order(collected)
    pay_order(cancelled)
    set_status(collected.id, OrderStatus.COLLECTED)
    set_status(cancelled.id, OrderStatus.CANCELLED)

    queue = kitchen.get("/api/kitchen/orders").get_json()["data"]["queue"]

    assert all(queue[status] == [] for status in queue)


def test_queue_status_filter(kitchen_client, student, menu):
    kitchen, _ = kitchen_client
    pay_order(make_order(student, menu))

    response = kitchen.get("/api/kitchen/orders?status=received")

    queue = response.get_json()["data"]["queue"]
    assert list(queue.keys()) == ["received"]


def test_queue_rejects_unknown_status_filter(kitchen_client):
    kitchen, _ = kitchen_client

    response = kitchen.get("/api/kitchen/orders?status=collected")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_FILTER"


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "limit=abc"])
def test_queue_rejects_bad_limit(kitchen_client, query):
    kitchen, _ = kitchen_client

    response = kitchen.get(f"/api/kitchen/orders?{query}")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_PAGINATION"


def test_queue_limit_applies_per_group(kitchen_client, student, menu):
    kitchen, _ = kitchen_client
    for _ in range(3):
        pay_order(make_order(student, menu))

    queue = kitchen.get("/api/kitchen/orders?limit=2").get_json()["data"]["queue"]

    assert len(queue["received"]) == 2


def test_student_cannot_see_queue(client):
    response = client.get("/api/kitchen/orders")

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_anonymous_cannot_see_queue(anon_client):
    response = anon_client.get("/api/kitchen/orders")

    assert response.status_code == 401


# ---------- Status changes ----------

def test_full_kitchen_flow_received_preparing_ready(kitchen_client, student, menu):
    kitchen, staff = kitchen_client
    order = make_order(student, menu)
    pay_order(order)

    preparing = patch_status(kitchen, order.id, "preparing")
    assert preparing.status_code == 200
    assert preparing.get_json()["data"]["order_status"] == "preparing"

    ready = patch_status(kitchen, order.id, "ready")
    assert ready.status_code == 200
    assert ready.get_json()["data"]["order_status"] == "ready"

    history = OrderStatusHistory.query.filter_by(order_id=order.id).order_by(OrderStatusHistory.id).all()
    transitions = [(row.previous_status, row.new_status) for row in history]
    assert transitions == [
        ("pending_payment", "received"),
        ("received", "preparing"),
        ("preparing", "ready"),
    ]
    assert history[0].changed_by is None          # payment confirmation is a system change
    assert history[1].changed_by == staff.id      # kitchen staff member is recorded
    assert history[2].changed_by == staff.id


def test_cannot_skip_a_step(kitchen_client, student, menu):
    kitchen, _ = kitchen_client
    order = make_order(student, menu)
    pay_order(order)

    response = patch_status(kitchen, order.id, "ready")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "INVALID_TRANSITION"
    assert reload(Order, order.id).order_status == OrderStatus.RECEIVED


def test_cannot_move_backwards(kitchen_client, student, menu):
    kitchen, _ = kitchen_client
    order = make_order(student, menu)
    pay_order(order)
    patch_status(kitchen, order.id, "preparing")
    patch_status(kitchen, order.id, "ready")

    response = patch_status(kitchen, order.id, "preparing")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "INVALID_TRANSITION"
    assert reload(Order, order.id).order_status == OrderStatus.READY


def test_unpaid_order_cannot_enter_preparation(kitchen_client, student, menu):
    kitchen, _ = kitchen_client
    order = make_order(student, menu)  # still pending_payment

    response = patch_status(kitchen, order.id, "preparing")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ORDER_NOT_PAID"
    assert reload(Order, order.id).order_status == OrderStatus.PENDING_PAYMENT


def test_kitchen_cannot_mark_collected(kitchen_client, student, menu):
    kitchen, _ = kitchen_client
    order = make_order(student, menu)
    pay_order(order)
    patch_status(kitchen, order.id, "preparing")
    patch_status(kitchen, order.id, "ready")

    response = patch_status(kitchen, order.id, "collected")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "USE_COLLECTION_FLOW"
    assert reload(Order, order.id).order_status == OrderStatus.READY


def test_kitchen_cannot_cancel(kitchen_client, student, menu):
    kitchen, _ = kitchen_client
    order = make_order(student, menu)
    pay_order(order)

    response = patch_status(kitchen, order.id, "cancelled")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "CANCELLATION_NOT_AVAILABLE"


@pytest.mark.parametrize("bad_status", ["bogus", "", "pending_payment", "received"])
def test_invalid_status_values_rejected(kitchen_client, student, menu, bad_status):
    kitchen, _ = kitchen_client
    order = make_order(student, menu)
    pay_order(order)

    response = patch_status(kitchen, order.id, bad_status)

    assert response.status_code in (400, 409)
    assert response.get_json()["error"]["code"] in ("INVALID_STATUS", "INVALID_TRANSITION")


def test_missing_status_field_rejected(kitchen_client, student, menu):
    kitchen, _ = kitchen_client
    order = make_order(student, menu)

    response = kitchen.patch(f"/api/kitchen/orders/{order.id}/status", json={})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_STATUS"


def test_status_update_for_missing_order_returns_404(kitchen_client):
    kitchen, _ = kitchen_client

    response = patch_status(kitchen, 99999, "preparing")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "ORDER_NOT_FOUND"


def test_student_cannot_update_status(client, student, menu):
    order = make_order(student, menu)
    pay_order(order)

    response = patch_status(client, order.id, "preparing")

    assert response.status_code == 403
    assert reload(Order, order.id).order_status == OrderStatus.RECEIVED


def test_admin_can_use_kitchen_routes(admin_client, student, menu):
    admin, _ = admin_client
    order = make_order(student, menu)
    pay_order(order)

    queue = admin.get("/api/kitchen/orders")
    update = patch_status(admin, order.id, "preparing")

    assert queue.status_code == 200
    assert update.status_code == 200


def test_admin_order_detail_includes_status_history(admin_client, kitchen_client, student, menu):
    admin, _ = admin_client
    kitchen, _ = kitchen_client
    order = make_order(student, menu)
    pay_order(order)
    patch_status(kitchen, order.id, "preparing")

    response = admin.get(f"/api/admin/orders/{order.id}")

    assert response.status_code == 200
    history = response.get_json()["data"]["status_history"]
    assert [(row["previous_status"], row["new_status"]) for row in history] == [
        ("pending_payment", "received"),
        ("received", "preparing"),
    ]
