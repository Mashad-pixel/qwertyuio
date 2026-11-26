"""Admin refund views: payments with refund totals, recent refunds, and refunds issued from the page."""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models.order import Order
from app.models.payment import PaymentRecordStatus
from app.models.user import User, UserRole
from app.services.order_service import create_order
from app.services.payment_service import _confirm_captured_payment, create_payment_order
from tests.session_helpers import issue_test_session


def make_user(email, role, name="Person"):
    user = User(name=name, email=email, role=role, is_active=True)
    user.set_password("StrongPass123!")
    db.session.add(user)
    db.session.commit()
    return user


def signed_in(app, user, mfa_verified=True):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["sid"] = issue_test_session(user, mfa_verified=mfa_verified)
    return client


def paid_order(student, menu, quantity=2):
    order, _ = create_order(student.id, [{"menu_item_id": menu["samosa"].id, "quantity": quantity}])
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
    return payment, db.session.get(Order, order.id)


def refund_client(status="processed"):
    fake = MagicMock()
    fake.payment.refund.return_value = {"id": f"rfnd_{uuid.uuid4().hex[:10]}", "status": status}
    return fake


@pytest.fixture
def admin(app):
    return make_user("admin@test.com", UserRole.ADMIN, name="Admin")


@pytest.fixture
def admin_client(app, admin):
    return signed_in(app, admin)


def payment_row(client, payment_id):
    rows = client.get("/api/admin/payments").get_json()["data"]["payments"]
    return next(row for row in rows if row["payment_id"] == payment_id)


def test_a_paid_payment_is_refundable_in_full(admin_client, student, menu):
    payment, order = paid_order(student, menu)
    row = payment_row(admin_client, payment.id)
    assert row["order_number"] == order.order_number
    assert row["amount_paise"] == order.total_paise
    assert row["refundable_paise"] == order.total_paise
    assert row["refunded_paise"] == 0


def test_a_processed_partial_refund_reduces_what_is_refundable(app, admin_client, admin, student, menu):
    from app.services.refund_service import request_refund

    payment, order = paid_order(student, menu)
    with patch("app.services.refund_service.get_razorpay_client", return_value=refund_client("processed")):
        request_refund(payment.id, admin.id, 1000, "Partly cancelled")
    row = payment_row(admin_client, payment.id)
    assert row["refunded_paise"] == 1000
    assert row["refundable_paise"] == order.total_paise - 1000
    assert row["payment_status"] == PaymentRecordStatus.PARTIALLY_REFUNDED


def test_a_pending_refund_is_held_back_from_what_can_be_refunded_again(app, admin_client, admin, student, menu):
    from app.services.refund_service import request_refund

    payment, order = paid_order(student, menu)
    with patch("app.services.refund_service.get_razorpay_client", return_value=refund_client("pending")):
        request_refund(payment.id, admin.id, 500, "Customer asked")
    row = payment_row(admin_client, payment.id)
    assert row["pending_refund_paise"] == 500
    assert row["refundable_paise"] == order.total_paise - 500


def test_an_unpaid_payment_shows_nothing_to_refund(admin_client, student, menu):
    from app.services.order_service import create_order as place

    order, _ = place(student.id, [{"menu_item_id": menu["samosa"].id, "quantity": 1}])
    fake = MagicMock()
    fake.order.create.return_value = {"id": f"order_{uuid.uuid4().hex[:12]}"}
    with patch("app.services.payment_service.get_razorpay_client", return_value=fake):
        payment, _ = create_payment_order(order.id, student.id)
    row = payment_row(admin_client, payment.id)
    assert row["payment_status"] == PaymentRecordStatus.CREATED
    assert row["refundable_paise"] == 0


def test_recent_refunds_show_status_order_and_reason(app, admin_client, admin, student, menu):
    from app.services.refund_service import request_refund

    payment, order = paid_order(student, menu)
    with patch("app.services.refund_service.get_razorpay_client", return_value=refund_client("pending")):
        request_refund(payment.id, admin.id, 700, "Kitchen closed")
    refunds = admin_client.get("/api/admin/payments/refunds").get_json()["data"]["refunds"]
    assert len(refunds) == 1
    assert refunds[0]["order_number"] == order.order_number
    assert refunds[0]["amount_paise"] == 700
    assert refunds[0]["status"] == "pending"
    assert refunds[0]["reason"] == "Kitchen closed"


def test_an_admin_can_issue_a_refund_through_the_api(app, admin_client, admin, student, menu):
    payment, order = paid_order(student, menu)
    with patch("app.services.refund_service.get_razorpay_client", return_value=refund_client("processed")):
        response = admin_client.post(f"/api/admin/payments/{payment.id}/refund", json={"amount_paise": 300, "reason": "Wrong item"})
    assert response.status_code == 201
    assert response.get_json()["data"]["status"] == "processed"


def test_refunding_more_than_is_left_is_refused_with_a_clear_code(app, admin_client, admin, student, menu):
    payment, order = paid_order(student, menu)
    response = admin_client.post(f"/api/admin/payments/{payment.id}/refund",
                                 json={"amount_paise": order.total_paise + 1, "reason": "Too much"})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "REFUND_TOO_LARGE"


@pytest.mark.parametrize("path", ["/api/admin/payments", "/api/admin/payments/refunds"])
def test_only_administrators_can_see_refund_views(app, student, path):
    assert signed_in(app, student).get(path).status_code == 403
    kitchen = make_user("kitchen@test.com", UserRole.KITCHEN, name="Kitchen")
    assert signed_in(app, kitchen).get(path).status_code == 403


@pytest.mark.parametrize("query", ["limit=0", "limit=500", "limit=abc"])
def test_bad_limits_are_refused(admin_client, query):
    assert admin_client.get(f"/api/admin/payments?{query}").status_code == 400
    assert admin_client.get(f"/api/admin/payments/refunds?{query}").status_code == 400
