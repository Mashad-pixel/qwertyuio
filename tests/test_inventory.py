from tests.session_helpers import issue_test_session
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models.collection_token import CollectionToken
from app.models.menu import MenuItem
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment, PaymentRecordStatus
from app.models.stock_reservation import ReservationStatus, StockReservation
from app.models.user import User, UserRole
from app.services.errors import OrderError
from app.services.order_service import create_order, expire_unpaid_orders
from app.services.payment_service import _confirm_captured_payment, create_payment_order

WEBHOOK_SECRET = "test_webhook_secret"


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


def order_with(user, menu_item, quantity):
    order, _ = create_order(user.id, [{"menu_item_id": menu_item.id, "quantity": quantity}])
    return order


def pay_order(order):
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


def backdate(order_id, minutes):
    """Make an order look like it was created `minutes` ago."""
    stored = db.session.get(Order, order_id)
    stored.created_at = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    db.session.commit()


def reload(model, pk):
    db.session.expire_all()
    return db.session.get(model, pk)


def stock_of(menu_item_id):
    item = reload(MenuItem, menu_item_id)
    return item.stock_quantity, item.reserved_quantity


def sign_body(body):
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def post_webhook(test_client, event_id, payload):
    body = json.dumps(payload).encode("utf-8")
    return test_client.post(
        "/api/payments/webhook",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": sign_body(body),
            "X-Razorpay-Event-Id": event_id,
        },
    )


@pytest.fixture
def admin_client(app):
    admin = make_user("admin@test.com", UserRole.ADMIN, name="Admin")
    return login_as(app.test_client(), admin)


@pytest.fixture
def kitchen_client(app):
    staff = make_user("kitchen@test.com", UserRole.KITCHEN, name="Kitchen")
    return login_as(app.test_client(), staff)


@pytest.fixture
def razorpay_fake(app):
    fake = MagicMock()
    fake.order.create.side_effect = lambda data: {"id": f"order_{uuid.uuid4().hex[:12]}"}
    with patch("app.services.payment_service.get_razorpay_client", return_value=fake):
        yield fake


# ---------- Reservations ----------

def test_order_reserves_stock(student, menu):
    item = menu["paneer_roll"]

    order = order_with(student, item, 1)

    stock, reserved = stock_of(item.id)
    assert (stock, reserved) == (2, 1)
    reservation = StockReservation.query.filter_by(order_id=order.id).one()
    assert reservation.status == ReservationStatus.RESERVED
    assert reservation.quantity == 1


def test_reservations_prevent_overselling(student, menu):
    other = make_user("other@test.com", UserRole.STUDENT, name="Other")
    item = menu["paneer_roll"]  # stock 2
    order_with(student, item, 2)

    with pytest.raises(OrderError) as exc:
        order_with(other, item, 1)

    assert exc.value.code == "INSUFFICIENT_STOCK"
    assert Order.query.count() == 1
    assert stock_of(item.id) == (2, 2)


def test_failed_reservation_leaves_no_order_behind(student, menu):
    other = make_user("other@test.com", UserRole.STUDENT, name="Other")
    item = menu["paneer_roll"]
    order_with(student, item, 2)

    with pytest.raises(OrderError):
        order_with(other, item, 1)

    assert Order.query.count() == 1
    assert StockReservation.query.count() == 1


def test_multiple_lines_for_same_item_are_combined_before_reserve(student, menu):
    item = menu["paneer_roll"]
    order, _ = create_order(student.id, [
        {"menu_item_id": item.id, "quantity": 1},
        {"menu_item_id": item.id, "quantity": 1},
    ])

    assert len(order.items) == 1
    assert order.items[0].quantity == 2
    assert stock_of(item.id) == (2, 2)


def test_untracked_items_do_not_create_reservations(student, menu):
    item = menu["tea"]  # stock_quantity is NULL
    order = order_with(student, item, 2)

    assert StockReservation.query.filter_by(order_id=order.id).count() == 0
    assert item.reserved_quantity == 0


# ---------- Payment and expiry ----------

def test_payment_commits_reservation(student, menu):
    item = menu["paneer_roll"]
    order = order_with(student, item, 1)
    reservation = StockReservation.query.filter_by(order_id=order.id).one()
    payment = pay_order(order)

    assert stock_of(item.id) == (1, 0)
    assert reload(StockReservation, reservation.id).status == ReservationStatus.COMMITTED
    assert reload(Payment, payment.id).status == PaymentRecordStatus.PAID


def test_expiry_releases_reserved_stock(student, menu, app):
    item = menu["paneer_roll"]
    order = order_with(student, item, 1)
    backdate(order.id, app.config["ORDER_PAYMENT_EXPIRY_MINUTES"] + 1)

    assert expire_unpaid_orders() == 1

    assert stock_of(item.id) == (2, 0)
    assert reload(Order, order.id).order_status == OrderStatus.CANCELLED
    reservation = StockReservation.query.filter_by(order_id=order.id).one()
    assert reservation.status == ReservationStatus.RELEASED


def test_create_new_order_sweeps_expired_reservations(student, menu, app):
    item = menu["paneer_roll"]
    old = order_with(student, item, 1)
    backdate(old.id, app.config["ORDER_PAYMENT_EXPIRY_MINUTES"] + 1)

    new = order_with(student, item, 2)

    assert reload(Order, old.id).order_status == OrderStatus.CANCELLED
    assert stock_of(item.id) == (2, 2)
    assert new.id != old.id


def test_payment_for_expired_order_is_refused(student, menu, app):
    item = menu["paneer_roll"]
    order = order_with(student, item, 1)
    backdate(order.id, app.config["ORDER_PAYMENT_EXPIRY_MINUTES"] + 1)
    fake = MagicMock()
    fake.order.create.return_value = {"id": "order_expired"}

    with patch("app.services.payment_service.get_razorpay_client", return_value=fake):
        with pytest.raises(OrderError) as exc:
            create_payment_order(order.id, student.id)

    assert exc.value.code == "ORDER_EXPIRED"
    fake.order.create.assert_not_called()
    assert stock_of(item.id) == (2, 0)


def test_late_captured_payment_after_expiry_is_flagged_for_refund(student, menu, app):
    item = menu["paneer_roll"]
    order = order_with(student, item, 1)
    payment = pay_order_created_without_capture(order)
    backdate(order.id, app.config["ORDER_PAYMENT_EXPIRY_MINUTES"] + 1)

    result, refund_required = _confirm_captured_payment(
        payment,
        provider_payment_id="pay_late",
        amount_paise=order.total_paise,
        currency="INR",
    )

    assert refund_required is True
    assert result.status == PaymentRecordStatus.REFUND_REQUIRED
    assert reload(Order, order.id).order_status == OrderStatus.CANCELLED
    assert stock_of(item.id) == (2, 0)


def pay_order_created_without_capture(order):
    fake = MagicMock()
    fake.order.create.return_value = {"id": f"order_{uuid.uuid4().hex[:12]}"}
    with patch("app.services.payment_service.get_razorpay_client", return_value=fake):
        payment, _ = create_payment_order(order.id, order.student_id)
    return payment


def test_late_captured_payment_after_cancellation_is_flagged_for_refund(student, menu, admin_client):
    item = menu["paneer_roll"]
    order = order_with(student, item, 1)
    payment = pay_order_created_without_capture(order)
    response = admin_client.post(f"/api/admin/orders/{order.id}/cancel", json={"reason": "Kitchen closed"})

    assert response.status_code == 200

    result, refund_required = _confirm_captured_payment(
        payment,
        provider_payment_id="pay_late_cancelled",
        amount_paise=order.total_paise,
        currency="INR",
    )

    assert refund_required is True
    assert result.status == PaymentRecordStatus.REFUND_REQUIRED
    assert reload(Order, order.id).order_status == OrderStatus.CANCELLED
    assert stock_of(item.id) == (2, 0)


def test_payment_failure_after_capture_is_ignored(student, menu, app):
    item = menu["paneer_roll"]
    order = order_with(student, item, 1)
    payment = pay_order(order)
    body = json.dumps({
        "event": "payment.failed",
        "payload": {"payment": {"entity": {
            "order_id": payment.provider_order_id,
            "id": payment.provider_payment_id,
            "error_code": "PAYMENT_ERROR",
            "error_description": "late failure event",
        }}}
    }).encode()

    response = app.test_client().post(
        "/api/payments/webhook", data=body,
        headers={"X-Razorpay-Signature": sign_body(body), "X-Razorpay-Event-Id": "evt-late-failure"},
    )

    assert response.status_code == 200
    assert reload(Payment, payment.id).status == PaymentRecordStatus.PAID


def test_admin_cancel_releases_unpaid_reservation(student, menu, admin_client):
    item = menu["paneer_roll"]
    order = order_with(student, item, 1)

    response = admin_client.post(f"/api/admin/orders/{order.id}/cancel", json={"reason": "Student requested"})

    assert response.status_code == 200
    assert stock_of(item.id) == (2, 0)
    assert reload(Order, order.id).order_status == OrderStatus.CANCELLED


def test_admin_cancel_paid_order_returns_stock_and_flags_refund(student, menu, admin_client):
    item = menu["paneer_roll"]
    order = order_with(student, item, 1)
    payment = pay_order(order)

    response = admin_client.post(f"/api/admin/orders/{order.id}/cancel", json={"reason": "Kitchen closed"})

    assert response.status_code == 200
    assert response.get_json()["data"]["refund_required"] is True
    assert stock_of(item.id) == (2, 0)
    assert reload(Payment, payment.id).status == PaymentRecordStatus.REFUND_REQUIRED
    assert reload(Order, order.id).order_status == OrderStatus.CANCELLED


def test_admin_cancel_stops_collection_code(student, menu, admin_client):
    item = menu["paneer_roll"]
    order = order_with(student, item, 1)
    pay_order(order)
    stored = reload(Order, order.id)
    stored.order_status = OrderStatus.READY
    db.session.commit()
    raw_token = "collection-token"
    db.session.add(CollectionToken(
        order_id=order.id,
        token_nonce="nonce",
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
    ))
    db.session.commit()

    response = admin_client.post(f"/api/admin/orders/{order.id}/cancel", json={"reason": "Kitchen closed"})

    assert response.status_code == 200
    token = CollectionToken.query.filter_by(order_id=order.id).one()
    assert token.used_at is not None


def test_cannot_cancel_collected_order(student, menu, admin_client):
    order = order_with(student, menu["tea"], 1)
    stored = reload(Order, order.id)
    stored.order_status = OrderStatus.COLLECTED
    db.session.commit()

    response = admin_client.post(f"/api/admin/orders/{order.id}/cancel", json={"reason": "Too late"})

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ORDER_ALREADY_COLLECTED"


def test_cancelled_order_cannot_be_cancelled_twice(student, menu, admin_client):
    order = order_with(student, menu["tea"], 1)
    first = admin_client.post(f"/api/admin/orders/{order.id}/cancel", json={"reason": "First"})
    second = admin_client.post(f"/api/admin/orders/{order.id}/cancel", json={"reason": "Second"})

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "ALREADY_CANCELLED"


def test_admin_cancel_requires_reason(admin_client, student, menu):
    order = order_with(student, menu["tea"], 1)
    response = admin_client.post(f"/api/admin/orders/{order.id}/cancel", json={})

    assert response.status_code == 200  # defaults to "Cancelled by admin"


def test_student_cannot_cancel_orders(student_client, student, menu):
    order = order_with(student, menu["tea"], 1)
    response = student_client.post(f"/api/admin/orders/{order.id}/cancel", json={"reason": "No"})

    assert response.status_code == 403
