from tests.session_helpers import issue_test_session
import hashlib
import hmac
import json

import pytest

from app.extensions import db
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.payment import Payment, PaymentRecordStatus
from app.models.payment_attempt import PaymentAttempt
from app.models.user import User, UserRole
from app.models.webhook_event import WebhookEvent, WebhookStatus
from app.services.order_service import create_order
from app.services.payment_service import create_payment_order

KEY_ID = "rzp_test_key_id"
KEY_SECRET = "test_key_secret"
WEBHOOK_SECRET = "test_webhook_secret"


# ---------- Fake Razorpay client (no network calls) ----------

class FakeOrderApi:
    def __init__(self):
        self.calls = []

    def create(self, data):
        self.calls.append(data)
        return {
            "id": f"order_fake_{len(self.calls)}",
            "amount": data["amount"],
            "currency": data["currency"],
            "status": "created",
        }


class FakePaymentApi:
    def __init__(self):
        self.payments = {}

    def fetch(self, payment_id):
        return self.payments[payment_id]


class FakeRazorpay:
    def __init__(self):
        self.order = FakeOrderApi()
        self.payment = FakePaymentApi()


@pytest.fixture
def fake_razorpay(app, monkeypatch):
    fake = FakeRazorpay()
    monkeypatch.setattr("app.services.payment_service.get_razorpay_client", lambda: fake)
    app.config["RAZORPAY_KEY_ID"] = KEY_ID
    app.config["RAZORPAY_KEY_SECRET"] = KEY_SECRET
    app.config["RAZORPAY_WEBHOOK_SECRET"] = WEBHOOK_SECRET
    return fake


# ---------- Helpers ----------

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


def make_order(user, menu, quantity=2):
    order, _ = create_order(
        user.id,
        [{"menu_item_id": menu["samosa"].id, "quantity": quantity}],
    )
    return order


def start_payment(test_client, order_id):
    response = test_client.post("/api/payments/create-order", json={"order_id": order_id})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["razorpay_order_id"]


def set_captured(fake, provider_order_id, payment_id, amount=3000, status="captured", currency="INR"):
    fake.payment.payments[payment_id] = {
        "id": payment_id,
        "order_id": provider_order_id,
        "amount": amount,
        "currency": currency,
        "status": status,
    }


def sign_checkout(provider_order_id, payment_id, secret=KEY_SECRET):
    message = f"{provider_order_id}|{payment_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def sign_body(body, secret=WEBHOOK_SECRET):
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def post_webhook(test_client, event_id, payload=None, signature=None, raw_body=None):
    body = raw_body if raw_body is not None else json.dumps(payload).encode("utf-8")
    sig = signature if signature is not None else sign_body(body)
    headers = {"Content-Type": "application/json", "X-Razorpay-Signature": sig}
    if event_id is not None:
        headers["X-Razorpay-Event-Id"] = event_id
    return test_client.post("/api/payments/webhook", data=body, headers=headers)


def captured_event(provider_order_id, payment_id, amount=3000, currency="INR"):
    return {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {
            "id": payment_id,
            "order_id": provider_order_id,
            "amount": amount,
            "currency": currency,
            "status": "captured",
        }}},
    }


def failed_event(provider_order_id, payment_id, reason="Card declined"):
    return {
        "event": "payment.failed",
        "payload": {"payment": {"entity": {
            "id": payment_id,
            "order_id": provider_order_id,
            "amount": 3000,
            "currency": "INR",
            "status": "failed",
            "error_description": reason,
        }}},
    }


def reload(model, pk):
    db.session.expire_all()
    return db.session.get(model, pk)


def verify_body(provider_order_id, payment_id, signature=None):
    return {
        "razorpay_order_id": provider_order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature if signature is not None else sign_checkout(provider_order_id, payment_id),
    }


# ---------- Create payment order ----------

def test_create_uses_server_side_amount(client, student, menu, fake_razorpay):
    order = make_order(student, menu, quantity=2)

    response = client.post("/api/payments/create-order", json={"order_id": order.id})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["amount_paise"] == 3000
    assert data["currency"] == "INR"
    assert data["key_id"] == KEY_ID
    assert data["order_number"] == order.order_number
    assert data["razorpay_order_id"].startswith("order_fake_")

    sent = fake_razorpay.order.calls[0]
    assert sent["amount"] == 3000
    assert sent["currency"] == "INR"
    assert sent["receipt"] == order.order_number
    assert "key_secret" not in json.dumps(data)


def test_create_reuses_open_payment(client, student, menu, fake_razorpay):
    order = make_order(student, menu)

    first = start_payment(client, order.id)
    second = start_payment(client, order.id)

    assert first == second
    assert len(fake_razorpay.order.calls) == 1


def test_create_for_another_students_order_is_404(client, app, menu, fake_razorpay):
    other = make_user("other@test.com", name="Other")
    order = make_order(other, menu)

    response = client.post("/api/payments/create-order", json={"order_id": order.id})

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "ORDER_NOT_FOUND"
    assert fake_razorpay.order.calls == []


def test_create_rejects_already_paid_order(client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    stored = db.session.get(Order, order.id)
    stored.payment_status = PaymentStatus.PAID
    stored.order_status = OrderStatus.RECEIVED
    db.session.commit()

    response = client.post("/api/payments/create-order", json={"order_id": order.id})

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ORDER_NOT_PAYABLE"


@pytest.mark.parametrize("bad_id", ["1", True, 0, -5, None, 1.5])
def test_create_rejects_bad_order_id(client, bad_id, fake_razorpay):
    response = client.post("/api/payments/create-order", json={"order_id": bad_id})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_ORDER_ID"


def test_create_without_keys_returns_503(client, student, menu):
    # No fake client and no keys configured, so the real client can't be built.
    order = make_order(student, menu)

    response = client.post("/api/payments/create-order", json={"order_id": order.id})

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "PAYMENTS_NOT_CONFIGURED"


def test_create_requires_login(anon_client, fake_razorpay):
    response = anon_client.post("/api/payments/create-order", json={"order_id": 1})

    assert response.status_code == 401


# ---------- Verify checkout ----------

def test_verify_success_marks_order_paid(client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)
    set_captured(fake_razorpay, rp_order, "pay_1", amount=3000)

    response = client.post("/api/payments/verify", json=verify_body(rp_order, "pay_1"))

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["order_status"] == "received"
    assert data["payment_status"] == "paid"

    stored_order = reload(Order, order.id)
    assert stored_order.order_status == OrderStatus.RECEIVED
    assert stored_order.payment_status == PaymentStatus.PAID

    stored_payment = Payment.query.filter_by(provider_order_id=rp_order).one()
    assert stored_payment.status == PaymentRecordStatus.PAID
    assert stored_payment.provider_payment_id == "pay_1"
    assert stored_payment.verified_at is not None

    assert PaymentAttempt.query.filter_by(order_id=order.id, status="succeeded").count() == 1


def test_verify_rejects_bad_signature(client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)
    set_captured(fake_razorpay, rp_order, "pay_1")

    wrong = sign_checkout(rp_order, "pay_1", secret="not-the-secret")
    response = client.post("/api/payments/verify", json=verify_body(rp_order, "pay_1", signature=wrong))

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_SIGNATURE"
    assert reload(Order, order.id).payment_status == PaymentStatus.PENDING


def test_verify_rejects_non_ascii_signature_without_crashing(client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)
    set_captured(fake_razorpay, rp_order, "pay_1")

    response = client.post(
        "/api/payments/verify",
        json=verify_body(rp_order, "pay_1", signature="pä€-signature"),
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_SIGNATURE"


def test_verify_rejects_amount_mismatch(client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)
    set_captured(fake_razorpay, rp_order, "pay_1", amount=9999)

    response = client.post("/api/payments/verify", json=verify_body(rp_order, "pay_1"))

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "PAYMENT_MISMATCH"
    assert reload(Order, order.id).payment_status == PaymentStatus.PENDING


def test_verify_rejects_payment_not_captured(client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)
    set_captured(fake_razorpay, rp_order, "pay_1", status="authorized")

    response = client.post("/api/payments/verify", json=verify_body(rp_order, "pay_1"))

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "PAYMENT_NOT_CAPTURED"
    assert reload(Order, order.id).payment_status == PaymentStatus.PENDING


def test_verify_rejects_payment_belonging_to_other_order(client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)
    set_captured(fake_razorpay, "order_someone_else", "pay_1")

    response = client.post("/api/payments/verify", json=verify_body(rp_order, "pay_1"))

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "PAYMENT_MISMATCH"


def test_verify_is_idempotent(client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)
    set_captured(fake_razorpay, rp_order, "pay_1")

    first = client.post("/api/payments/verify", json=verify_body(rp_order, "pay_1"))
    second = client.post("/api/payments/verify", json=verify_body(rp_order, "pay_1"))

    assert first.status_code == 200
    assert second.status_code == 200
    assert PaymentAttempt.query.filter_by(order_id=order.id, status="succeeded").count() == 1
    assert Payment.query.filter_by(provider_order_id=rp_order).count() == 1


def test_verify_for_another_students_payment_is_404(client, student, menu, fake_razorpay):
    # Create the other student's payment through the service, not over HTTP.
    # Flask-Login caches the user in g for the whole test app context, so a request
    # from another logged-in client would leak its user into later requests.
    other = make_user("other@test.com", name="Other")
    other_order = make_order(other, menu)
    payment, _ = create_payment_order(other_order.id, other.id)
    rp_order = payment.provider_order_id
    set_captured(fake_razorpay, rp_order, "pay_1")

    response = client.post("/api/payments/verify", json=verify_body(rp_order, "pay_1"))

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "PAYMENT_NOT_FOUND"
    assert reload(Order, other_order.id).payment_status == PaymentStatus.PENDING


def test_verify_missing_fields_rejected(client, fake_razorpay):
    response = client.post("/api/payments/verify", json={"razorpay_order_id": "order_x"})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "MISSING_FIELDS"


def test_verify_requires_login(anon_client, fake_razorpay):
    response = anon_client.post("/api/payments/verify", json=verify_body("order_x", "pay_x"))

    assert response.status_code == 401


# ---------- Webhooks ----------

def test_webhook_captured_marks_order_paid(anon_client, client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)

    response = post_webhook(anon_client, "evt_1", captured_event(rp_order, "pay_w1"))

    assert response.status_code == 200
    assert response.get_json()["data"]["outcome"] == "processed"

    stored_order = reload(Order, order.id)
    assert stored_order.order_status == OrderStatus.RECEIVED
    assert stored_order.payment_status == PaymentStatus.PAID
    assert WebhookEvent.query.filter_by(provider_event_id="evt_1").one().processing_status == "processed"


def test_webhook_rejects_bad_signature(anon_client, client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)

    response = post_webhook(
        anon_client,
        "evt_bad",
        captured_event(rp_order, "pay_w1"),
        signature=sign_body(b"tampered", secret=WEBHOOK_SECRET),
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_SIGNATURE"
    assert reload(Order, order.id).payment_status == PaymentStatus.PENDING
    assert WebhookEvent.query.filter_by(provider_event_id="evt_bad").count() == 0


def test_webhook_rejects_missing_signature(anon_client, client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)

    response = post_webhook(anon_client, "evt_nosig", captured_event(rp_order, "pay_w1"), signature="")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_SIGNATURE"


def test_webhook_duplicate_delivery_processed_once(anon_client, client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)
    event = captured_event(rp_order, "pay_w1")

    first = post_webhook(anon_client, "evt_dup", event)
    second = post_webhook(anon_client, "evt_dup", event)

    assert first.get_json()["data"]["outcome"] == "processed"
    assert second.status_code == 200
    assert second.get_json()["data"]["outcome"] == "duplicate"
    assert PaymentAttempt.query.filter_by(order_id=order.id, status="succeeded").count() == 1


def test_webhook_after_verify_does_not_double_count(anon_client, client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)
    set_captured(fake_razorpay, rp_order, "pay_1")
    client.post("/api/payments/verify", json=verify_body(rp_order, "pay_1"))

    response = post_webhook(anon_client, "evt_after_verify", captured_event(rp_order, "pay_1"))

    assert response.status_code == 200
    stored_order = reload(Order, order.id)
    assert stored_order.order_status == OrderStatus.RECEIVED
    assert PaymentAttempt.query.filter_by(order_id=order.id, status="succeeded").count() == 1


def test_webhook_failed_payment_keeps_order_pending(anon_client, client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)

    response = post_webhook(anon_client, "evt_fail", failed_event(rp_order, "pay_f1", "Card declined"))

    assert response.status_code == 200
    assert response.get_json()["data"]["outcome"] == "processed"

    stored_order = reload(Order, order.id)
    assert stored_order.order_status == OrderStatus.PENDING_PAYMENT
    assert stored_order.payment_status == PaymentStatus.PENDING

    attempt = PaymentAttempt.query.filter_by(order_id=order.id, status="failed").one()
    assert attempt.failure_reason == "Card declined"
    assert attempt.provider_payment_id == "pay_f1"


def test_webhook_late_failure_after_success_is_ignored(anon_client, client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)
    set_captured(fake_razorpay, rp_order, "pay_1")
    client.post("/api/payments/verify", json=verify_body(rp_order, "pay_1"))

    response = post_webhook(anon_client, "evt_late_fail", failed_event(rp_order, "pay_2"))

    assert response.get_json()["data"]["outcome"] == "ignored"
    assert reload(Order, order.id).order_status == OrderStatus.RECEIVED


def test_webhook_unknown_payment_is_ignored(anon_client, fake_razorpay):
    response = post_webhook(anon_client, "evt_unknown", captured_event("order_unknown", "pay_x"))

    assert response.status_code == 200
    assert response.get_json()["data"]["outcome"] == "ignored"


def test_webhook_unknown_event_type_is_ignored(anon_client, fake_razorpay):
    response = post_webhook(anon_client, "evt_other", {"event": "refund.processed", "payload": {}})

    assert response.status_code == 200
    assert response.get_json()["data"]["outcome"] == "ignored"


def test_webhook_amount_mismatch_fails_and_asks_for_retry(anon_client, client, student, menu, fake_razorpay):
    order = make_order(student, menu)
    rp_order = start_payment(client, order.id)

    response = post_webhook(anon_client, "evt_mismatch", captured_event(rp_order, "pay_w1", amount=1))

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "WEBHOOK_PROCESSING_FAILED"
    assert WebhookEvent.query.filter_by(provider_event_id="evt_mismatch").one().processing_status == WebhookStatus.FAILED
    assert reload(Order, order.id).payment_status == PaymentStatus.PENDING


def test_webhook_missing_event_id_rejected(anon_client, fake_razorpay):
    response = post_webhook(anon_client, None, captured_event("order_x", "pay_x"))

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_EVENT_ID"


def test_webhook_invalid_json_with_valid_signature_rejected(anon_client, fake_razorpay):
    body = b"this is not json"
    response = post_webhook(anon_client, "evt_badjson", raw_body=body)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_JSON"


def test_webhook_not_configured_returns_503(anon_client, app):
    app.config["RAZORPAY_WEBHOOK_SECRET"] = ""
    response = post_webhook(anon_client, "evt_cfg", captured_event("order_x", "pay_x"), signature="abc")

    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "WEBHOOKS_NOT_CONFIGURED"



def test_kitchen_role_cannot_create_or_verify_student_payment(app):
    kitchen = make_user("kitchen-payment-role@test.com", role=UserRole.KITCHEN, name="Kitchen User")
    kitchen_client = app.test_client()
    login_as(kitchen_client, kitchen)

    create_response = kitchen_client.post("/api/payments/create-order", json={"order_id": 1})
    verify_response = kitchen_client.post(
        "/api/payments/verify",
        json=verify_body("order_not_real", "payment_not_real"),
    )
    assert create_response.status_code == 403
    assert verify_response.status_code == 403
    assert create_response.get_json()["error"]["code"] == "FORBIDDEN"
    assert verify_response.get_json()["error"]["code"] == "FORBIDDEN"
