from tests.session_helpers import issue_test_session
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models.collection_token import CollectionToken
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


def patch_status(test_client, order_id, status):
    return test_client.patch(
        f"/api/kitchen/orders/{order_id}/status",
        json={"status": status},
    )


def make_ready(kitchen, student, menu):
    order = make_order(student, menu)
    pay_order(order)
    patch_status(kitchen, order.id, "preparing")
    response = patch_status(kitchen, order.id, "ready")
    assert response.status_code == 200
    return order


def get_qr(client, order_id):
    return client.get(f"/api/orders/{order_id}/collection-qr")


def verify(kitchen, token):
    return kitchen.post("/api/kitchen/collection/verify", json={"token": token})


def confirm(kitchen, token):
    return kitchen.post("/api/kitchen/collection/confirm", json={"token": token})


def reload(model, pk):
    db.session.expire_all()
    return db.session.get(model, pk)


def sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.fixture
def kitchen(app):
    staff = make_user("kitchen@test.com", UserRole.KITCHEN, name="Kitchen Staff")
    return login_as(app.test_client(), staff)


@pytest.fixture
def staff_user(app):
    return make_user("kitchen2@test.com", UserRole.KITCHEN, name="Second Staff")


# ---------- Student QR ----------

def test_ready_order_gives_student_a_qr(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)

    response = get_qr(client, order.id)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data["token"]) >= 40
    assert data["order_number"] == order.order_number
    assert "expires_at" in data
    assert response.headers["Cache-Control"] == "no-store"


def test_only_hash_of_token_is_stored(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)
    raw = get_qr(client, order.id).get_json()["data"]["token"]

    stored = CollectionToken.query.filter_by(order_id=order.id).all()

    assert len(stored) == 1
    assert stored[0].token_hash == sha256(raw)
    assert raw not in (stored[0].token_hash, stored[0].token_nonce)


def test_student_sees_same_qr_after_reload(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)

    first = get_qr(client, order.id).get_json()["data"]["token"]
    second = get_qr(client, order.id).get_json()["data"]["token"]

    assert first == second
    assert CollectionToken.query.filter_by(order_id=order.id).count() == 1


def test_qr_not_available_before_ready(client, student, menu):
    order = make_order(student, menu)
    pay_order(order)  # paid but still "received"

    response = get_qr(client, order.id)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "COLLECTION_NOT_AVAILABLE"
    assert CollectionToken.query.filter_by(order_id=order.id).count() == 0


def test_qr_not_available_for_unpaid_order(client, student, menu):
    order = make_order(student, menu)  # pending_payment

    response = get_qr(client, order.id)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "COLLECTION_NOT_AVAILABLE"
    assert CollectionToken.query.filter_by(order_id=order.id).count() == 0


def test_student_cannot_get_another_students_qr(app, client, kitchen, menu):
    other = make_user("other@test.com", UserRole.STUDENT, name="Other")
    order = make_ready(kitchen, other, menu)

    response = get_qr(client, order.id)

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "ORDER_NOT_FOUND"


def test_qr_requires_login(anon_client, kitchen, menu):
    response = anon_client.get("/api/orders/1/collection-qr")

    assert response.status_code == 401


def test_expired_token_is_replaced_on_next_request(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)
    old_raw = get_qr(client, order.id).get_json()["data"]["token"]

    old_row = CollectionToken.query.filter_by(order_id=order.id).one()
    old_row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.session.commit()

    new_raw = get_qr(client, order.id).get_json()["data"]["token"]

    assert new_raw != old_raw
    assert verify(kitchen, new_raw).status_code == 200
    assert verify(kitchen, old_raw).get_json()["error"]["code"] == "TOKEN_EXPIRED"


# ---------- Kitchen verify (preview) ----------

def test_verify_shows_order_without_collecting(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)
    raw = get_qr(client, order.id).get_json()["data"]["token"]

    response = verify(kitchen, raw)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["order_number"] == order.order_number
    assert data["order_status"] == "ready"
    assert "student" not in data
    assert reload(Order, order.id).order_status == OrderStatus.READY


def test_verify_rejects_unknown_token(kitchen):
    response = verify(kitchen, "not-a-real-token")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_TOKEN"


def test_verify_requires_token_field(kitchen):
    response = kitchen.post("/api/kitchen/collection/verify", json={})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "MISSING_TOKEN"


# ---------- Kitchen confirm ----------

def test_confirm_marks_collected_and_records_staff(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)
    raw = get_qr(client, order.id).get_json()["data"]["token"]
    staff_id = kitchen.get("/api/auth/me").get_json()["data"]["id"]

    response = confirm(kitchen, raw)

    assert response.status_code == 200
    assert response.get_json()["data"]["order_status"] == "collected"

    stored = reload(Order, order.id)
    assert stored.order_status == OrderStatus.COLLECTED
    assert stored.payment_status == PaymentStatus.PAID

    history = OrderStatusHistory.query.filter_by(order_id=order.id, new_status="collected").one()
    assert history.previous_status == "ready"
    assert history.changed_by == staff_id
    assert history.notes == "Collected with QR code"

    assert CollectionToken.query.filter_by(order_id=order.id).one().used_at is not None


def test_token_cannot_be_used_twice(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)
    raw = get_qr(client, order.id).get_json()["data"]["token"]

    first = confirm(kitchen, raw)
    second = confirm(kitchen, raw)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "TOKEN_ALREADY_USED"
    assert OrderStatusHistory.query.filter_by(order_id=order.id, new_status="collected").count() == 1


def test_verify_after_collection_reports_used(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)
    raw = get_qr(client, order.id).get_json()["data"]["token"]
    confirm(kitchen, raw)

    response = verify(kitchen, raw)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "TOKEN_ALREADY_USED"


def test_student_qr_unavailable_after_collection(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)
    raw = get_qr(client, order.id).get_json()["data"]["token"]
    confirm(kitchen, raw)

    response = get_qr(client, order.id)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "COLLECTION_NOT_AVAILABLE"


def test_two_staff_cannot_both_confirm(app, client, kitchen, staff_user, student, menu):
    order = make_ready(kitchen, student, menu)
    raw = get_qr(client, order.id).get_json()["data"]["token"]
    other_staff_client = login_as(app.test_client(), staff_user)

    first = confirm(kitchen, raw)
    second = confirm(other_staff_client, raw)

    assert first.status_code == 200
    assert second.status_code == 409
    assert OrderStatusHistory.query.filter_by(order_id=order.id, new_status="collected").count() == 1


def test_expired_token_cannot_collect(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)
    raw = get_qr(client, order.id).get_json()["data"]["token"]

    row = CollectionToken.query.filter_by(order_id=order.id).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.session.commit()

    response = confirm(kitchen, raw)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "TOKEN_EXPIRED"
    assert reload(Order, order.id).order_status == OrderStatus.READY


def test_token_rejected_if_order_no_longer_paid(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)
    raw = get_qr(client, order.id).get_json()["data"]["token"]

    stored = db.session.get(Order, order.id)
    stored.payment_status = PaymentStatus.PENDING
    db.session.commit()

    response = confirm(kitchen, raw)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ORDER_NOT_PAID"
    assert CollectionToken.query.filter_by(order_id=order.id).one().used_at is None


def test_token_rejected_if_order_not_ready(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)
    raw = get_qr(client, order.id).get_json()["data"]["token"]

    stored = db.session.get(Order, order.id)
    stored.order_status = OrderStatus.PREPARING
    db.session.commit()

    response = confirm(kitchen, raw)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ORDER_NOT_READY"
    assert CollectionToken.query.filter_by(order_id=order.id).one().used_at is None


def test_kitchen_cannot_skip_qr_to_collected(kitchen, student, menu):
    order = make_ready(kitchen, student, menu)

    response = patch_status(kitchen, order.id, "collected")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "USE_COLLECTION_FLOW"


def test_student_cannot_verify_or_confirm(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)
    raw = get_qr(client, order.id).get_json()["data"]["token"]

    verify_response = client.post("/api/kitchen/collection/verify", json={"token": raw})
    confirm_response = client.post("/api/kitchen/collection/confirm", json={"token": raw})

    assert verify_response.status_code == 403
    assert confirm_response.status_code == 403
    assert reload(Order, order.id).order_status == OrderStatus.READY


def test_ready_hook_creates_exactly_one_token(client, kitchen, student, menu):
    order = make_ready(kitchen, student, menu)

    assert CollectionToken.query.filter_by(order_id=order.id).count() == 1
    assert OrderStatusHistory.query.filter_by(order_id=order.id, new_status="ready").count() == 1
