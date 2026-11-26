"""Password recovery: email codes, reset tokens, backup codes, support requests and session revocation."""
from datetime import timedelta

import pytest

from app.extensions import db
from app.models.recovery import AccountRecoveryRequest, PasswordRecoveryChallenge, RecoveryCode
from app.models.user import User, UserRole
from app.services.otp_delivery import DeliveryError, send_recovery_code
from app.services.time_utils import utcnow

NEW_PASSWORD = "BrandNew456!"


def outbox(app):
    return app.extensions.get("recovery_outbox", [])


def start(client, identifier):
    return client.post("/api/forgot/start", json={"identifier": identifier})


def latest_code(app):
    return outbox(app)[-1]["code"]


def verify(client, identifier, code):
    return client.post("/api/forgot/verify", json={"identifier": identifier, "otp": code})


def reset(client, token, password=NEW_PASSWORD):
    return client.post("/api/forgot/reset", json={"resetToken": token, "password": password})


def make_user_fresh_cooldown(app, email):
    """Pretend the last code was sent long ago, so another request is allowed."""
    user = User.query.filter_by(email=email).one()
    for row in PasswordRecoveryChallenge.query.filter_by(user_id=user.id).all():
        row.last_sent_at = utcnow() - timedelta(minutes=5)
        row.created_at = utcnow() - timedelta(minutes=5)
    db.session.commit()


# ---- sending codes -------------------------------------------------------------------------

def test_start_sends_one_code_and_stores_only_a_hash(app, student, anon_client):
    response = start(anon_client, student.email)

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert len(outbox(app)) == 1
    code = latest_code(app)
    assert len(code) == 6 and code.isdigit()

    rows = PasswordRecoveryChallenge.query.filter_by(user_id=student.id).all()
    assert len(rows) == 1
    assert code not in rows[0].code_hash
    assert rows[0].code_hash != code


def test_unknown_email_gets_the_same_reply_and_no_code(app, student, anon_client):
    known = start(anon_client, student.email).get_json()
    unknown = start(anon_client, "nobody@test.com").get_json()

    assert known == unknown
    assert len(outbox(app)) == 1  # only the known account got a code


def test_email_is_matched_case_insensitively(app, student, anon_client):
    start(anon_client, "  STUDENT@Test.com ")
    assert len(outbox(app)) == 1


def test_phone_recovery_is_reported_as_unavailable(app, anon_client):
    response = start(anon_client, "+91 98765 43210")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "PHONE_RECOVERY_UNAVAILABLE"
    assert outbox(app) == []


def test_invalid_identifier_is_rejected(anon_client):
    response = start(anon_client, "not-an-email")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_IDENTIFIER"


def test_missing_body_is_rejected(anon_client):
    response = anon_client.post("/api/forgot/start")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_JSON"


def test_resend_inside_cooldown_sends_nothing(app, student, anon_client):
    start(anon_client, student.email)
    response = anon_client.post("/api/forgot/resend", json={"identifier": student.email})

    assert response.status_code == 200
    assert len(outbox(app)) == 1


def test_resend_after_cooldown_sends_a_new_code_and_retires_the_old_one(app, student, anon_client):
    start(anon_client, student.email)
    old_code = latest_code(app)
    make_user_fresh_cooldown(app, student.email)

    anon_client.post("/api/forgot/resend", json={"identifier": student.email})
    new_code = latest_code(app)

    assert len(outbox(app)) == 2
    assert verify(anon_client, student.email, old_code).status_code == 400
    assert verify(anon_client, student.email, new_code).status_code == 200


def test_hourly_limit_stops_code_floods(app, student, anon_client, monkeypatch):
    monkeypatch.setitem(app.config, "RECOVERY_MAX_CODES_PER_HOUR", 2)
    for _ in range(4):
        start(anon_client, student.email)
        make_user_fresh_cooldown(app, student.email)
    assert len(outbox(app)) == 2


def test_delivery_failure_still_answers_generically(app, student, anon_client, monkeypatch):
    monkeypatch.setitem(app.config, "RECOVERY_DELIVERY", "smtp")
    monkeypatch.setitem(app.config, "SMTP_HOST", "")  # no mail server configured

    response = start(anon_client, student.email)

    assert response.status_code == 200
    assert "sent" in response.get_json()["message"]
    assert outbox(app) == []


def test_console_delivery_is_refused_in_production_settings(app, student, monkeypatch):
    monkeypatch.setitem(app.config, "RECOVERY_DELIVERY", "console")
    monkeypatch.setitem(app.config, "ALLOW_CONSOLE_DELIVERY", False)
    with pytest.raises(DeliveryError):
        send_recovery_code(student.email, "123456")


# ---- verifying codes -----------------------------------------------------------------------

def test_correct_code_gives_a_reset_token_that_sets_the_password(app, student, anon_client):
    start(anon_client, student.email)
    token = verify(anon_client, student.email, latest_code(app)).get_json()["data"]["resetToken"]

    assert reset(anon_client, token).status_code == 200

    login = anon_client.post("/api/auth/login", json={"email": student.email, "password": NEW_PASSWORD})
    assert login.status_code == 200
    old = anon_client.post("/api/auth/login", json={"email": student.email, "password": "StrongPass123!"})
    assert old.status_code == 401


def test_code_locks_after_too_many_wrong_tries(app, student, anon_client):
    start(anon_client, student.email)
    real = latest_code(app)
    wrong = "000000" if real != "000000" else "111111"

    for _ in range(5):
        assert verify(anon_client, student.email, wrong).status_code == 400
    # Even the right code no longer works once the attempts are used up.
    assert verify(anon_client, student.email, real).status_code == 400


def test_expired_code_is_rejected(app, student, anon_client):
    start(anon_client, student.email)
    code = latest_code(app)
    row = PasswordRecoveryChallenge.query.filter_by(user_id=student.id).one()
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()

    assert verify(anon_client, student.email, code).status_code == 400


def test_code_must_be_six_digits(app, student, anon_client):
    start(anon_client, student.email)
    assert verify(anon_client, student.email, "12345").status_code == 400
    assert verify(anon_client, student.email, "abcdef").status_code == 400


def test_reset_token_is_single_use(app, student, anon_client):
    start(anon_client, student.email)
    token = verify(anon_client, student.email, latest_code(app)).get_json()["data"]["resetToken"]

    assert reset(anon_client, token).status_code == 200
    second = reset(anon_client, token, "AnotherPass789!")
    assert second.status_code == 400
    assert second.get_json()["error"]["code"] == "INVALID_RESET"


def test_reset_token_expires(app, student, anon_client):
    start(anon_client, student.email)
    token = verify(anon_client, student.email, latest_code(app)).get_json()["data"]["resetToken"]
    row = PasswordRecoveryChallenge.query.filter_by(user_id=student.id).one()
    row.reset_expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()

    assert reset(anon_client, token).status_code == 400


def test_reset_rejects_weak_and_unchanged_passwords(app, student, anon_client):
    start(anon_client, student.email)
    token = verify(anon_client, student.email, latest_code(app)).get_json()["data"]["resetToken"]

    weak = reset(anon_client, token, "short")
    assert weak.status_code == 400 and weak.get_json()["error"]["code"] == "INVALID_PASSWORD"

    same = reset(anon_client, token, "StrongPass123!")
    assert same.status_code == 400 and same.get_json()["error"]["code"] == "PASSWORD_UNCHANGED"

    # A rejected attempt does not spend the token.
    assert reset(anon_client, token).status_code == 200


def test_reset_signs_out_existing_sessions(app, student, anon_client):
    # Log in first, so the session is older than the reset.
    logged_in = app.test_client()
    assert logged_in.post("/api/auth/login", json={"email": student.email, "password": "StrongPass123!"}).status_code == 200
    assert logged_in.get("/api/auth/me").status_code == 200

    start(anon_client, student.email)
    token = verify(anon_client, student.email, latest_code(app)).get_json()["data"]["resetToken"]
    reset(anon_client, token)

    assert logged_in.get("/api/auth/me").status_code == 401


# ---- backup recovery codes -----------------------------------------------------------------

def test_backup_codes_are_shown_once_and_stored_hashed(app, student):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(student.id)
        sess["_fresh"] = True

    response = client.post("/api/auth/recovery-codes")
    assert response.status_code == 201
    codes = response.get_json()["data"]["codes"]
    assert len(codes) == 8
    assert all(len(code) == 14 and code.count("-") == 2 for code in codes)

    stored = RecoveryCode.query.filter_by(user_id=student.id).all()
    assert len(stored) == 8
    raw = {code.replace("-", "") for code in codes}
    assert not any(row.code_hash in raw for row in stored)


def test_backup_code_works_once_and_then_is_spent(app, student, anon_client):
    codes = create_codes(app, student)

    first = anon_client.post("/api/recovery/code", json={"identifier": student.email, "code": codes[0]})
    assert first.status_code == 200
    token = first.get_json()["data"]["resetToken"]
    assert reset(anon_client, token).status_code == 200

    again = anon_client.post("/api/recovery/code", json={"identifier": student.email, "code": codes[0]})
    assert again.status_code == 400


def test_backup_code_is_forgiving_about_case_and_hyphens(app, student, anon_client):
    codes = create_codes(app, student)
    messy = codes[1].replace("-", " ").lower()
    response = anon_client.post("/api/recovery/code", json={"identifier": student.email, "code": messy})
    assert response.status_code == 200


def test_wrong_backup_code_is_generic(app, student, anon_client):
    create_codes(app, student)
    response = anon_client.post("/api/recovery/code", json={"identifier": student.email, "code": "AAAA-BBBB-CCCC"})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_BACKUP_CODE"

    unknown = anon_client.post("/api/recovery/code", json={"identifier": "x@test.com", "code": "AAAA-BBBB-CCCC"})
    assert unknown.get_json()["message"] == response.get_json()["message"]


def test_regenerating_codes_invalidates_unused_ones(app, student, anon_client):
    old = create_codes(app, student)
    create_codes(app, student)

    response = anon_client.post("/api/recovery/code", json={"identifier": student.email, "code": old[0]})
    assert response.status_code == 400


def create_codes(app, student):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(student.id)
        sess["_fresh"] = True
    return client.post("/api/auth/recovery-codes").get_json()["data"]["codes"]


# ---- support requests ----------------------------------------------------------------------

def support_payload(**overrides):
    payload = {
        "name": "Asha Rao",
        "identifier": "student@test.com",
        "contactEmail": "asha@example.com",
        "createdEst": "March 2025",
        "lastLoginEst": "last month",
        "reason": "I lost access to my old email address.",
        "extra": "",
    }
    payload.update(overrides)
    return payload


def test_support_request_is_stored_with_a_reference_and_hides_the_match(app, student, anon_client):
    response = anon_client.post("/api/recovery/request", json=support_payload())

    assert response.status_code == 201
    ref = response.get_json()["data"]["ref"]
    assert ref.startswith("REC-")

    row = AccountRecoveryRequest.query.filter_by(ref=ref).one()
    assert row.user_id == student.id  # recorded for staff...
    unknown = anon_client.post("/api/recovery/request", json=support_payload(identifier="nobody@test.com"))
    assert unknown.status_code == 201  # ...but the reply is the same either way


def test_support_request_validates_its_fields(anon_client):
    short = anon_client.post("/api/recovery/request", json=support_payload(reason="short"))
    assert short.status_code == 400

    bad_contact = anon_client.post("/api/recovery/request", json=support_payload(contactEmail="nope"))
    assert bad_contact.status_code == 400


def test_only_admins_can_read_support_requests(app, student, anon_client):
    anon_client.post("/api/recovery/request", json=support_payload())

    admin = User(name="Admin", email="admin-recovery@test.com", role=UserRole.ADMIN, is_active=True)
    admin.set_password("StrongPass123!")
    db.session.add(admin)
    db.session.commit()

    admin_client = app.test_client()
    with admin_client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True
    response = admin_client.get("/api/admin/recovery-requests")
    assert response.status_code == 200
    requests = response.get_json()["data"]["requests"]
    assert len(requests) == 1
    assert requests[0]["contact_email"] == "asha@example.com"
    assert "password" not in str(requests[0]).lower()
