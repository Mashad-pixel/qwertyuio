"""Live QR + GPS presence verification: end-to-end rules through the real routes.

Coordinates in the test configuration are (0, 0). A reading at latitude 0.002 is about 222 m away.
"""
import time
from datetime import timedelta

import pytest

from app.extensions import db
from app.models.order import Order
from app.models.presence import PresenceRedemption, PresenceSession, PresenceToken
from app.models.user import User, UserRole
from app.services.canteen_service import update_status
from app.services.errors import OrderError
from app.services.order_service import create_order
from app.services.presence_service import (
    hash_session,
    hash_token,
    issue_display_token,
    prune_presence_records,
)
from app.services.time_utils import utcnow
from presence_helpers import issue_test_presence_session

VERIFY = "/api/presence/verify"
DISPLAY = "/api/presence/display-code"
REVOKE = "/api/presence/revoke"
SETTINGS = "/api/presence/settings"
ORDERS = "/api/orders"


# ---------- helpers ----------

def make_user(email, role, name="Test User"):
    user = User(name=name, email=email, role=role, is_active=True)
    user.set_password("StrongPass123!")
    db.session.add(user)
    db.session.commit()
    return user


def logged_in(app, user, *, auto_presence=False):
    """Client logged in as `user`. Auto-presence is off by default so tests control the flow."""
    client = app.test_client()
    client.auto_presence = auto_presence
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return client


def gps(latitude=0.0, longitude=0.0, accuracy=10.0, timestamp=None):
    return {
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": accuracy,
        "timestamp": int(time.time() * 1000) if timestamp is None else timestamp,
    }


def verify(client, token, **overrides):
    body = {"token": token, **gps()}
    body.update(overrides)
    return client.post(VERIFY, json=body)


def order_body(menu, key="samosa", quantity=1):
    return {"items": [{"menu_item_id": menu[key].id, "quantity": quantity}]}


@pytest.fixture
def staff(app):
    return make_user("screen@test.com", UserRole.KITCHEN, "Screen")


@pytest.fixture
def staff_client(app, staff):
    return logged_in(app, staff)


@pytest.fixture
def other_student(app):
    return make_user("other@test.com", UserRole.STUDENT, "Other Student")


def live_code(staff):
    """A raw live QR token, issued through the same service the display route uses."""
    raw, _ = issue_display_token(staff.id)
    return raw


def verified_session(app, student):
    """Verify through the real route and return the session token."""
    client = logged_in(app, student)
    token = live_code_for_test(app, student)
    response = verify(client, token)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["session_token"]


def live_code_for_test(app, issuer):
    raw, _ = issue_display_token(issuer.id)
    return raw


# ---------- display endpoint (authorized canteen screen only) ----------

def test_display_code_requires_login(app):
    response = app.test_client().get(DISPLAY)
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTH_REQUIRED"


def test_display_code_is_forbidden_to_students(app, student):
    response = logged_in(app, student).get(DISPLAY)
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_display_code_returns_svg_ttl_and_no_store_for_staff(staff_client):
    response = staff_client.get(DISPLAY)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["qr_svg"].startswith("<svg")
    assert data["ttl_seconds"] == 10
    assert response.headers["Cache-Control"] == "no-store"


def test_each_display_request_issues_a_new_code(app, staff_client):
    first = staff_client.get(DISPLAY).get_json()["data"]["qr_svg"]
    second = staff_client.get(DISPLAY).get_json()["data"]["qr_svg"]
    assert first != second
    assert PresenceToken.query.count() == 2


def test_only_a_keyed_digest_of_the_token_is_stored(app, staff):
    raw = live_code(staff)
    row = PresenceToken.query.one()
    assert row.token_hash == hash_token(raw)
    assert row.token_hash != raw
    assert len(row.token_hash) == 64


def test_display_code_fails_closed_when_location_is_not_configured(app, staff_client):
    app.config["CANTEEN_LATITUDE"] = None
    app.config["CANTEEN_LONGITUDE"] = None
    response = staff_client.get(DISPLAY)
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "PRESENCE_NOT_CONFIGURED"


def test_public_settings_expose_radius_but_never_coordinates(app):
    data = app.test_client().get(SETTINGS).get_json()["data"]
    assert data["radius_meters"] == 100
    assert data["max_accuracy_meters"] == 75
    assert data["session_ttl_seconds"] == 180
    assert "latitude" not in data and "longitude" not in data


# ---------- revocation ----------

def test_revoke_requires_staff(app, student):
    response = logged_in(app, student).post(REVOKE)
    assert response.status_code == 403


def test_revoked_code_is_rejected(app, staff, staff_client, student):
    raw = live_code(staff)
    response = staff_client.post(REVOKE)
    assert response.status_code == 200
    assert response.get_json()["data"]["revoked"] >= 1

    rejected = verify(logged_in(app, student), raw)
    assert rejected.status_code == 409
    assert rejected.get_json()["error"]["code"] == "QR_CODE_REVOKED"


# ---------- student verification: valid, expired, replayed, shared ----------

def test_valid_code_and_gps_create_one_single_use_session(app, staff, student):
    response = verify(logged_in(app, student), live_code(staff))
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert len(data["session_token"]) >= 32
    assert data["expires_in_seconds"] == 180
    assert data["single_use"] is True
    assert response.headers["Cache-Control"] == "no-store"

    assert PresenceRedemption.query.count() == 1
    session_row = PresenceSession.query.one()
    assert session_row.student_id == student.id
    assert session_row.consumed_at is None
    assert session_row.session_hash == hash_session(data["session_token"])


def test_gps_coordinates_are_not_stored_anywhere(app, staff, student):
    response = verify(logged_in(app, student), live_code(staff), latitude=0.0004, longitude=0.0003)
    assert response.status_code == 201
    redemption = PresenceRedemption.query.one()
    assert set(c.name for c in PresenceRedemption.__table__.columns) == {
        "id", "token_id", "student_id", "redeemed_at", "distance_meters", "accuracy_meters",
    }
    assert redemption.distance_meters == 56  # rounded metres, not coordinates


def test_several_students_can_scan_the_same_active_code(app, staff, student, other_student):
    code = live_code(staff)
    first = verify(logged_in(app, student), code)
    second = verify(logged_in(app, other_student), code)
    assert first.status_code == 201
    assert second.status_code == 201
    assert PresenceRedemption.query.count() == 2


def test_same_student_cannot_replay_the_same_code(app, staff, student):
    code = live_code(staff)
    client = logged_in(app, student)
    assert verify(client, code).status_code == 201

    replay = verify(client, code)
    assert replay.status_code == 409
    assert replay.get_json()["error"]["code"] == "QR_CODE_ALREADY_USED"
    assert PresenceRedemption.query.count() == 1


def test_expired_code_is_rejected_even_with_valid_gps(app, staff, student):
    code = live_code(staff)
    row = PresenceToken.query.order_by(PresenceToken.id.desc()).first()
    row.expires_at = utcnow() - timedelta(seconds=1)  # what a screenshot taken 11 seconds ago looks like
    db.session.commit()

    response = verify(logged_in(app, student), code)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "QR_CODE_EXPIRED"
    assert PresenceRedemption.query.count() == 0


def test_unknown_or_malformed_code_is_rejected(app, student):
    client = logged_in(app, student)
    assert verify(client, "A" * 43).get_json()["error"]["code"] == "INVALID_QR_CODE"
    assert verify(client, "short").get_json()["error"]["code"] == "INVALID_QR_CODE"
    assert verify(client, None).get_json()["error"]["code"] == "INVALID_QR_CODE"


def test_gps_outside_the_geofence_is_rejected_and_does_not_burn_the_code(app, staff, student):
    code = live_code(staff)
    client = logged_in(app, student)

    far = verify(client, code, latitude=0.002)  # about 222 m away
    assert far.status_code == 403
    assert far.get_json()["error"]["code"] == "OUTSIDE_CANTEEN_AREA"
    assert PresenceRedemption.query.count() == 0

    # Walking closer and retrying with the same code, still live, must succeed.
    assert verify(client, code, latitude=0.0004).status_code == 201


def test_inaccurate_gps_is_rejected(app, staff, student):
    response = verify(logged_in(app, student), live_code(staff), accuracy=120.0)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "LOCATION_ACCURACY_TOO_LOW"


def test_stale_gps_reading_is_rejected(app, staff, student):
    old = int(time.time() * 1000) - 120_000
    response = verify(logged_in(app, student), live_code(staff), timestamp=old)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "LOCATION_STALE"


@pytest.mark.parametrize("field, bad", [
    ("latitude", "0.0"), ("latitude", 999.0), ("longitude", None), ("accuracy", -1), ("timestamp", "now"),
])
def test_malformed_location_fields_are_rejected(app, staff, student, field, bad):
    response = verify(logged_in(app, student), live_code(staff), **{field: bad})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "LOCATION_INVALID"


def test_verify_rejects_non_json_body(app, student):
    response = logged_in(app, student).post(VERIFY, data="x", content_type="text/plain")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_JSON"


def test_verify_fails_closed_when_location_is_not_configured(app, staff, student):
    code = live_code(staff)  # issued while the canteen is still configured
    app.config["CANTEEN_LATITUDE"] = None
    app.config["CANTEEN_LONGITUDE"] = None
    response = verify(logged_in(app, student), code)
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "PRESENCE_NOT_CONFIGURED"


# ---------- unauthorized users ----------

def test_verify_requires_login(app, staff):
    response = verify(app.test_client(), live_code(staff))
    assert response.status_code == 401


def test_staff_cannot_verify_presence(app, staff, staff_client):
    response = verify(staff_client, live_code(staff))
    assert response.status_code == 403
    assert PresenceRedemption.query.count() == 0


def test_deactivated_student_loses_access_immediately(app, staff, student):
    client = logged_in(app, student)
    student.is_active = False
    db.session.commit()
    assert verify(client, live_code(staff)).status_code == 401


def test_verify_requires_csrf_token_when_protection_is_enabled(app, staff, student):
    app.config["WTF_CSRF_ENABLED"] = True
    response = verify(logged_in(app, student), live_code(staff))
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "CSRF_TOKEN_INVALID"


# ---------- order API enforcement (direct API, no frontend involved) ----------

def test_order_without_verification_is_rejected(app, menu, student):
    response = logged_in(app, student).post(ORDERS, json=order_body(menu))
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "PRESENCE_VERIFICATION_REQUIRED"
    assert Order.query.count() == 0


def test_order_with_verification_succeeds_and_consumes_the_session(app, staff, student, menu):
    session_token = verified_session(app, student)
    response = logged_in(app, student).post(
        ORDERS,
        json=order_body(menu),
        headers={"X-Presence-Session": session_token},
    )
    assert response.status_code == 201

    order = Order.query.one()
    session_row = PresenceSession.query.one()
    assert session_row.consumed_at is not None
    assert session_row.order_id == order.id


def test_one_session_authorises_only_one_order(app, staff, student, menu):
    session_token = verified_session(app, student)
    client = logged_in(app, student)
    headers = {"X-Presence-Session": session_token}

    assert client.post(ORDERS, json=order_body(menu), headers=headers).status_code == 201
    second = client.post(ORDERS, json=order_body(menu, quantity=2), headers=headers)
    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "PRESENCE_SESSION_USED"
    assert Order.query.count() == 1


def test_session_belonging_to_another_student_is_rejected(app, student, other_student, menu):
    stolen = issue_test_presence_session(student.id)
    response = logged_in(app, other_student).post(
        ORDERS,
        json=order_body(menu),
        headers={"X-Presence-Session": stolen},
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "PRESENCE_SESSION_INVALID"
    assert Order.query.count() == 0


def test_expired_session_is_rejected(app, student, menu):
    expired = issue_test_presence_session(student.id, expires_at=utcnow() - timedelta(seconds=1))
    response = logged_in(app, student).post(
        ORDERS,
        json=order_body(menu),
        headers={"X-Presence-Session": expired},
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "PRESENCE_SESSION_EXPIRED"
    assert Order.query.count() == 0


@pytest.mark.parametrize("forged", ["A" * 43, "not a token", "x" * 500, ""])
def test_forged_or_malformed_session_is_rejected(app, student, menu, forged):
    response = logged_in(app, student).post(
        ORDERS,
        json=order_body(menu),
        headers={"X-Presence-Session": forged},
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] in {"PRESENCE_SESSION_INVALID", "PRESENCE_VERIFICATION_REQUIRED"}
    assert Order.query.count() == 0


def test_pricing_failure_does_not_consume_the_session(app, student, menu):
    session_token = issue_test_presence_session(student.id)
    client = logged_in(app, student)
    headers = {"X-Presence-Session": session_token}

    # Only 2 paneer rolls exist, so 3 must fail before anything is written.
    too_many = client.post(ORDERS, json=order_body(menu, key="paneer_roll", quantity=3), headers=headers)
    assert too_many.status_code == 409
    assert too_many.get_json()["error"]["code"] == "INSUFFICIENT_STOCK"

    retry = client.post(ORDERS, json=order_body(menu), headers=headers)
    assert retry.status_code == 201


def test_session_is_not_consumed_when_the_order_transaction_fails(app, student, menu, monkeypatch):
    session_token = issue_test_presence_session(student.id)

    def fail_after_consumption(order_id, lines):
        raise OrderError("STOCK_SYSTEM_DOWN", "Simulated failure after the session was marked used.", 500)

    monkeypatch.setattr("app.services.order_service.reserve_stock", fail_after_consumption)
    with pytest.raises(OrderError):
        create_order(
            student.id,
            [{"menu_item_id": menu["samosa"].id, "quantity": 1}],
            presence_session_token=session_token,
        )

    row = PresenceSession.query.filter_by(session_hash=hash_session(session_token)).one()
    assert row.consumed_at is None
    assert row.order_id is None
    assert Order.query.count() == 0


def test_closing_the_canteen_does_not_consume_the_session(app, student, menu):
    session_token = issue_test_presence_session(student.id)
    client = logged_in(app, student)
    headers = {"X-Presence-Session": session_token}

    update_status({"is_accepting_orders": False})
    closed = client.post(ORDERS, json=order_body(menu), headers=headers)
    assert closed.status_code == 409
    assert closed.get_json()["error"]["code"] == "CANTEEN_CLOSED"

    update_status({"is_accepting_orders": True})
    assert client.post(ORDERS, json=order_body(menu), headers=headers).status_code == 201


def test_staff_cannot_place_orders_even_with_a_session(app, staff, menu):
    session_token = issue_test_presence_session(staff.id)
    response = logged_in(app, staff).post(
        ORDERS,
        json=order_body(menu),
        headers={"X-Presence-Session": session_token},
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_idempotent_retry_returns_the_original_order_without_a_second_session(app, student, menu):
    first_session = issue_test_presence_session(student.id)
    second_session = issue_test_presence_session(student.id)
    client = logged_in(app, student)

    created = client.post(
        ORDERS,
        json=order_body(menu),
        headers={"X-Presence-Session": first_session, "Idempotency-Key": "retry-key-1"},
    )
    assert created.status_code == 201

    retried = client.post(
        ORDERS,
        json=order_body(menu),
        headers={"X-Presence-Session": second_session, "Idempotency-Key": "retry-key-1"},
    )
    assert retried.status_code == 200
    assert Order.query.count() == 1

    untouched = PresenceSession.query.filter_by(session_hash=hash_session(second_session)).one()
    assert untouched.consumed_at is None


# ---------- retention ----------

def test_prune_removes_old_records_and_keeps_recent_ones(app, student):
    issue_test_presence_session(student.id)
    old = utcnow() - timedelta(days=30)
    for row in PresenceSession.query.all():
        row.created_at = old
        row.expires_at = old + timedelta(seconds=180)
    for row in PresenceRedemption.query.all():
        row.redeemed_at = old
    for row in PresenceToken.query.all():
        row.issued_at = old
        row.expires_at = old + timedelta(seconds=10)
    db.session.commit()

    issue_test_presence_session(student.id)  # a recent one that must survive
    counts = prune_presence_records()

    assert counts == {"sessions": 1, "redemptions": 1, "tokens": 1}
    assert PresenceSession.query.count() == 1
    assert PresenceRedemption.query.count() == 1


# ---------- student self-registration ----------

def test_student_can_register_and_is_signed_in(app):
    client = app.test_client()
    response = client.post("/api/auth/register", json={
        "name": "New Student",
        "email": "  NEW@test.com ",
        "password": "LongEnough1",
    })
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["role"] == "STUDENT"
    assert data["email"] == "new@test.com"
    assert "csrf_token" in data
    assert client.get("/api/auth/me").status_code == 200


def test_registration_always_creates_a_student_even_if_a_role_is_sent(app):
    response = app.test_client().post("/api/auth/register", json={
        "name": "Sneaky",
        "email": "sneaky@test.com",
        "password": "LongEnough1",
        "role": "ADMIN",
    })
    assert response.status_code == 201
    assert response.get_json()["data"]["role"] == "STUDENT"


def test_duplicate_registration_is_rejected(app, student):
    response = app.test_client().post("/api/auth/register", json={
        "name": "Again",
        "email": "student@test.com",
        "password": "LongEnough1",
    })
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "EMAIL_UNAVAILABLE"


@pytest.mark.parametrize("payload", [
    {"name": "", "email": "a@test.com", "password": "LongEnough1"},
    {"name": "A", "email": "not-an-email", "password": "LongEnough1"},
    {"name": "A", "email": "a@test.com", "password": "short"},
    {"name": "A", "email": "a@test.com"},
])
def test_registration_validates_input(app, payload):
    response = app.test_client().post("/api/auth/register", json=payload)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_REGISTRATION"


# ---------- frontend delivery (QR links must open a real page) ----------

def test_student_verify_page_is_served_same_origin(app):
    response = app.test_client().get("/frontend/student/verify.html")
    assert response.status_code == 200
    assert b"Verify" in response.data


def test_frontend_route_cannot_read_files_outside_the_frontend_folder(app):
    response = app.test_client().get("/frontend/..%2F..%2Fapp%2Fconfig.py")
    assert response.status_code == 404
