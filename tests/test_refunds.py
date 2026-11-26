from tests.session_helpers import issue_test_session
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.payment import Payment, PaymentRecordStatus
from app.models.refund import Refund, RefundStatus
from app.models.user import User, UserRole
from app.services.errors import OrderError
from app.services.order_service import create_order
from app.services.payment_service import _confirm_captured_payment, create_payment_order
from app.services.refund_service import request_refund

WEBHOOK_SECRET = "test_webhook_secret"


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


def create_paid_payment(student, menu, key="samosa"):
    order, _ = create_order(student.id, [{"menu_item_id": menu[key].id, "quantity": 2}])
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
    return payment


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


# ---------- Refunds ----------

def test_full_refund_processed_immediately(app, student, menu, admin_client):
    payment = create_paid_payment(student, menu)
    fake = MagicMock()
    fake.payment.refund.return_value = {
        "id": "rfnd_full",
        "status": "processed",
    }

    with patch("app.services.refund_service.get_razorpay_client", return_value=fake):
        refund, updated_payment, order = request_refund(payment.id, 1, None, "Customer asked")

    assert refund.amount_paise == payment.amount_paise
    assert refund.status == RefundStatus.PROCESSED
    assert updated_payment.status == PaymentRecordStatus.REFUNDED
    assert order.payment_status == PaymentStatus.REFUNDED


def test_partial_refund_waits_for_webhook(app, student, menu, admin_client):
    payment = create_paid_payment(student, menu)
    fake = MagicMock()
    fake.payment.refund.return_value = {
        "id": "rfnd_partial",
        "status": "pending",
    }

    with patch("app.services.refund_service.get_razorpay_client", return_value=fake):
        refund, updated_payment, order = request_refund(payment.id, 1, 500, "Partial")

    assert refund.amount_paise == 500
    assert refund.status == RefundStatus.PENDING
    assert updated_payment.status == PaymentRecordStatus.REFUND_REQUIRED
    assert order.payment_status == PaymentStatus.PAID


def test_processed_webhook_marks_refund_and_payment(app, student, menu, admin_client):
    payment = create_paid_payment(student, menu)
    fake = MagicMock()
    fake.payment.refund.return_value = {"id": "rfnd_webhook", "status": "pending"}
    with patch("app.services.refund_service.get_razorpay_client", return_value=fake):
        refund, _, _ = request_refund(payment.id, 1, 500, "Partial")

    response = post_webhook(app.test_client(), "evt-refund-ok", {
        "event": "refund.processed",
        "payload": {"refund": {"entity": {"id": refund.provider_refund_id}}},
    })

    assert response.status_code == 200
    assert Refund.query.filter_by(id=refund.id).one().status == RefundStatus.PROCESSED
    assert Payment.query.filter_by(id=payment.id).one().status == PaymentRecordStatus.PARTIALLY_REFUNDED


def test_failed_webhook_keeps_captured_payment(app, student, menu, admin_client):
    payment = create_paid_payment(student, menu)
    fake = MagicMock()
    fake.payment.refund.return_value = {"id": "rfnd_fail", "status": "pending"}
    with patch("app.services.refund_service.get_razorpay_client", return_value=fake):
        refund, _, _ = request_refund(payment.id, 1, 500, "Partial")

    response = post_webhook(app.test_client(), "evt-refund-failed", {
        "event": "refund.failed",
        "payload": {"refund": {"entity": {"id": refund.provider_refund_id}}},
    })

    assert response.status_code == 200
    assert Refund.query.filter_by(id=refund.id).one().status == RefundStatus.FAILED
    assert Payment.query.filter_by(id=payment.id).one().status == PaymentRecordStatus.PAID


def test_refund_webhook_arriving_before_refund_record_is_saved(app, student, menu, admin_client):
    payment = create_paid_payment(student, menu)
    provider_refund_id = "rfnd_race"
    body = json.dumps({
        "event": "refund.processed",
        "payload": {"refund": {"entity": {"id": provider_refund_id}}},
    }).encode()

    # During the provider call, the webhook runs before request_refund saves the refund row.
    # It gets a 404 so Razorpay retries. The request then commits and a retry can succeed.
    def provider_refund(*args, **kwargs):
        response = post_webhook(app.test_client(), "evt-refund-race", {
            "event": "refund.processed",
            "payload": {"refund": {"entity": {"id": provider_refund_id}}},
        })
        assert response.status_code == 500
        return {"id": provider_refund_id, "status": "pending"}

    fake = MagicMock()
    fake.payment.refund.side_effect = provider_refund
    with patch("app.services.refund_service.get_razorpay_client", return_value=fake):
        refund, _, _ = request_refund(payment.id, 1, 500, "Race")

    retry = post_webhook(app.test_client(), "evt-refund-race", {
        "event": "refund.processed",
        "payload": {"refund": {"entity": {"id": provider_refund_id}}},
    })

    assert retry.status_code == 200
    assert refund.status == RefundStatus.PROCESSED
    assert Refund.query.filter_by(id=refund.id).one().status == RefundStatus.PROCESSED


def test_partial_refunds_cannot_exceed_payment(app, student, menu, admin_client):
    payment = create_paid_payment(student, menu)
    fake = MagicMock()
    fake.payment.refund.return_value = {"id": "rfnd_one", "status": "pending"}

    with patch("app.services.refund_service.get_razorpay_client", return_value=fake):
        request_refund(payment.id, 1, payment.amount_paise - 100, "First")
        with pytest.raises(OrderError) as exc:
            request_refund(payment.id, 1, 200, "Too much")

    assert exc.value.code == "REFUND_TOO_LARGE"


def test_student_cannot_request_refund(student_client, student, menu):
    payment = create_paid_payment(student, menu)
    response = student_client.post(
        f"/api/admin/payments/{payment.id}/refund",
        json={"amount_paise": 100, "reason": "Try"},
    )
    assert response.status_code == 403


def test_refund_requires_reason(admin_client, student, menu):
    payment = create_paid_payment(student, menu)
    response = admin_client.post(f"/api/admin/payments/{payment.id}/refund", json={"amount_paise": 100})
    assert response.status_code == 400


def test_student_cannot_view_refunds(student_client, student, menu):
    payment = create_paid_payment(student, menu)
    response = student_client.get(f"/api/admin/payments/{payment.id}/refunds")
    assert response.status_code == 403


def test_unauthenticated_cannot_request_refund(anon_client, student, menu):
    payment = create_paid_payment(student, menu)
    response = anon_client.post(f"/api/admin/payments/{payment.id}/refund", json={"reason": "No"})
    assert response.status_code == 401
