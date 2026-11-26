"""Password recovery: email codes, reset tokens, backup codes, support requests."""
import re
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.security.production_checks import production_problems
from app.extensions import db, limiter
from app.models.recovery import OtpChallenge, PasswordResetToken, RecoveryCode, RecoveryRequest
from app.models.user import User, UserRole
from app.services.mail_service import MailError
from app.services.time_utils import utcnow
from tests.session_helpers import issue_test_session

NEW_PASSWORD = "BrandNew2025"


def outbox(app):
    return app.extensions.get("mail_outbox", [])


def code_from_outbox(app):
    matches = re.findall(r"code is (\d{6})", outbox(app)[-1]["body"])
    assert matches, "email should contain a 6-digit code"
    return matches[0]


def start(client, identifier="student@test.com"):
    return client.post("/api/forgot/start", json={"identifier": identifier})


def logged_in_client(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["sid"] = issue_test_session(user)
    return client


# ---------- Starting a reset ----------

def test_unknown_and_known_emails_get_the_same_response(app, anon_client, student):
    unknown = start(anon_client, "nobody@test.com")
    known = start(anon_client, "student@test.com")
    assert unknown.status_code == known.status_code == 200
    assert unknown.get_json() == known.get_json()
    # Only the real account is emailed.
    assert [mail["to"] for mail in outbox(app)] == ["student@test.com"]


def test_start_emails_a_six_digit_code_that_is_not_stored_in_plain_text(app, anon_client, student):
    start(anon_client)
    code = code_from_outbox(app)
    challenge = OtpChallenge.query.filter_by(user_id=student.id).one()
    assert challenge.code_hash != code
    assert len(challenge.code_hash) == 64


def test_mobile_numbers_are_refused_clearly(anon_client):
    response = start(anon_client, "98765 43210")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "MOBILE_RESET_UNAVAILABLE"


def test_invalid_identifier_is_refused(anon_client):
    response = start(anon_client, "not an address")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_IDENTIFIER"


def test_reset_refuses_clearly_when_email_is_not_configured(app, anon_client, student):
    app.config["MAIL_BACKEND"] = "smtp"
    app.config["MAIL_HOST"] = ""
    response = start(anon_client)
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "MAIL_NOT_CONFIGURED"


def test_a_failed_delivery_looks_the_same_as_success(app, anon_client, student):
    with patch("app.routes.recovery.recovery_service.send_mail", side_effect=MailError("down")):
        response = start(anon_client)
    assert response.status_code == 200
    assert response.get_json()["success"] is True


# ---------- Checking the code ----------

def test_correct_code_gives_a_single_use_reset_token(app, anon_client, student):
    start(anon_client)
    code = code_from_outbox(app)
    response = anon_client.post("/api/forgot/verify", json={"identifier": "student@test.com", "otp": code})
    assert response.status_code == 200
    token = response.get_json()["data"]["resetToken"]
    assert token
    assert PasswordResetToken.query.one().token_hash != token

    again = anon_client.post("/api/forgot/verify", json={"identifier": "student@test.com", "otp": code})
    assert again.status_code == 400  # the code was consumed


def test_wrong_codes_give_one_generic_message(app, anon_client, student):
    start(anon_client)
    wrong = anon_client.post("/api/forgot/verify", json={"identifier": "student@test.com", "otp": "000000"})
    unknown = anon_client.post("/api/forgot/verify", json={"identifier": "nobody@test.com", "otp": "000000"})
    assert wrong.status_code == unknown.status_code == 400
    assert wrong.get_json()["message"] == unknown.get_json()["message"]


def test_a_code_locks_after_five_wrong_attempts_even_if_then_correct(app, anon_client, student):
    start(anon_client)
    code = code_from_outbox(app)
    for _ in range(5):
        anon_client.post("/api/forgot/verify", json={"identifier": "student@test.com", "otp": "000000"})
    locked = anon_client.post("/api/forgot/verify", json={"identifier": "student@test.com", "otp": code})
    assert locked.status_code == 400


def test_an_expired_code_is_rejected(app, anon_client, student):
    start(anon_client)
    code = code_from_outbox(app)
    challenge = OtpChallenge.query.filter_by(user_id=student.id).one()
    challenge.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    response = anon_client.post("/api/forgot/verify", json={"identifier": "student@test.com", "otp": code})
    assert response.status_code == 400


def test_a_new_code_retires_the_previous_one(app, anon_client, student):
    from app.services.recovery_service import start_email_recovery

    start(anon_client)
    first = code_from_outbox(app)
    # The HTTP cooldown is tested separately. Here the service is asked for a second code directly.
    start_email_recovery("student@test.com")
    second = code_from_outbox(app)
    if second != first:
        old = anon_client.post("/api/forgot/verify", json={"identifier": "student@test.com", "otp": first})
        assert old.status_code == 400
    current = anon_client.post("/api/forgot/verify", json={"identifier": "student@test.com", "otp": second})
    assert current.status_code == 200


# ---------- Setting the new password ----------

def _reset_token(app, client, student):
    start(client)
    code = code_from_outbox(app)
    response = client.post("/api/forgot/verify", json={"identifier": "student@test.com", "otp": code})
    return response.get_json()["data"]["resetToken"]


def test_reset_changes_the_password_and_signs_out_every_session(app, anon_client, student):
    signed_in = logged_in_client(app, student)
    assert signed_in.get("/api/auth/me").status_code == 200

    token = _reset_token(app, anon_client, student)
    response = anon_client.post("/api/forgot/reset", json={"resetToken": token, "password": NEW_PASSWORD})
    assert response.status_code == 200

    assert signed_in.get("/api/auth/me").status_code == 401
    login = anon_client.post("/api/auth/login", json={"email": "student@test.com", "password": NEW_PASSWORD})
    assert login.status_code == 200
    old = anon_client.post("/api/auth/login", json={"email": "student@test.com", "password": "StrongPass123!"})
    assert old.status_code == 401


def test_a_reset_token_works_once(app, anon_client, student):
    token = _reset_token(app, anon_client, student)
    first = anon_client.post("/api/forgot/reset", json={"resetToken": token, "password": NEW_PASSWORD})
    second = anon_client.post("/api/forgot/reset", json={"resetToken": token, "password": "Another2025"})
    assert first.status_code == 200
    assert second.status_code == 400


def test_an_expired_reset_token_is_rejected(app, anon_client, student):
    token = _reset_token(app, anon_client, student)
    row = PasswordResetToken.query.one()
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    response = anon_client.post("/api/forgot/reset", json={"resetToken": token, "password": NEW_PASSWORD})
    assert response.status_code == 400


def test_a_weak_password_keeps_the_token_usable(app, anon_client, student):
    token = _reset_token(app, anon_client, student)
    weak = anon_client.post("/api/forgot/reset", json={"resetToken": token, "password": "onlyletters"})
    assert weak.status_code == 400
    assert weak.get_json()["error"]["code"] == "PASSWORD_INVALID"
    good = anon_client.post("/api/forgot/reset", json={"resetToken": token, "password": NEW_PASSWORD})
    assert good.status_code == 200


def test_only_a_hash_of_the_reset_token_is_stored(app, anon_client, student):
    token = _reset_token(app, anon_client, student)
    stored = PasswordResetToken.query.one()
    assert stored.token_hash != token
    assert len(stored.token_hash) == 64


# ---------- Rate limits ----------

def test_resend_within_the_cooldown_is_refused_with_a_json_message(monkeypatch):
    from app.config import TestingConfig
    from app import create_app

    monkeypatch.setattr(TestingConfig, "RATELIMIT_ENABLED", True)
    limited = create_app("testing")
    with limited.app_context():
        db.create_all()
        from app.models.user import User as U
        account = U(name="R", email="r@test.com", role="STUDENT", is_active=True)
        account.set_password("StrongPass123!")
        db.session.add(account)
        db.session.commit()
    try:
        limiter.reset()
        limiter.enabled = True
        client = limited.test_client()
        assert client.post("/api/forgot/start", json={"identifier": "r@test.com"}).status_code == 200
        blocked = client.post("/api/forgot/resend", json={"identifier": "r@test.com"})
        assert blocked.status_code == 429
        assert blocked.is_json
        assert blocked.get_json()["error"]["code"] == "RATE_LIMITED"
    finally:
        limiter.enabled = False
        limiter.reset()
        with limited.app_context():
            db.session.remove()
            db.drop_all()


# ---------- Backup recovery codes ----------

def test_backup_codes_need_the_current_password_and_work_once(app, student):
    client = logged_in_client(app, student)
    refused = client.post("/api/auth/recovery-codes", json={"password": "wrong"})
    assert refused.status_code == 400

    issued = client.post("/api/auth/recovery-codes", json={"password": "StrongPass123!"})
    assert issued.status_code == 200
    codes = issued.get_json()["data"]["codes"]
    assert len(codes) == 10
    assert all(re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", c) for c in codes)
    assert codes[0] not in [row.code_hash for row in RecoveryCode.query.all()]

    anon = app.test_client()
    first = anon.post("/api/recovery/code", json={"identifier": "student@test.com", "code": codes[0].lower()})
    assert first.status_code == 200
    assert first.get_json()["data"]["resetToken"]
    again = anon.post("/api/recovery/code", json={"identifier": "student@test.com", "code": codes[0]})
    assert again.status_code == 400


def test_regenerating_backup_codes_retires_the_old_ones(app, student):
    client = logged_in_client(app, student)
    old_codes = client.post("/api/auth/recovery-codes", json={"password": "StrongPass123!"}).get_json()["data"]["codes"]
    client.post("/api/auth/recovery-codes", json={"password": "StrongPass123!"})
    anon = app.test_client()
    response = anon.post("/api/recovery/code", json={"identifier": "student@test.com", "code": old_codes[0]})
    assert response.status_code == 400


def test_a_wrong_backup_code_gives_the_generic_message(app, anon_client, student):
    response = anon_client.post("/api/recovery/code", json={"identifier": "student@test.com", "code": "ABCD-EFGH-JKLM"})
    assert response.status_code == 400
    assert response.get_json()["message"].startswith("That recovery code")


# ---------- Support requests ----------

SUPPORT = {
    "name": "Asha Rao",
    "identifier": "student@test.com",
    "contactEmail": "asha@example.com",
    "createdEst": "March 2025",
    "lastLoginEst": "last month",
    "reason": "I lost my phone and cannot get the code.",
    "extra": "",
}


def test_a_support_request_is_stored_and_gets_a_reference(app, anon_client):
    response = anon_client.post("/api/recovery/request", json=SUPPORT)
    assert response.status_code == 201
    reference = response.get_json()["data"]["ref"]
    assert reference.startswith("TRY-")
    stored = RecoveryRequest.query.filter_by(reference=reference).one()
    assert stored.status == "received"
    assert stored.identifier == "student@test.com"


def test_a_support_request_with_missing_details_is_refused(anon_client):
    response = anon_client.post("/api/recovery/request", json={**SUPPORT, "reason": "short", "contactEmail": "nope"})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_FAILED"


def test_only_administrators_can_read_support_requests(app, anon_client, student):
    anon_client.post("/api/recovery/request", json=SUPPORT)
    assert logged_in_client(app, student).get("/api/admin/recovery-requests").status_code == 403

    admin = User(name="Admin", email="admin@test.com", role=UserRole.ADMIN, is_active=True)
    admin.set_password("StrongPass123!")
    db.session.add(admin)
    db.session.commit()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True
        sess["sid"] = issue_test_session(admin, mfa_verified=True)
    rows = client.get("/api/admin/recovery-requests").get_json()["data"]["requests"]
    assert len(rows) == 1 and rows[0]["reference"].startswith("TRY-")


# ---------- Production safety ----------

def test_production_refuses_to_send_codes_to_the_log():
    config = {"SECRET_KEY": "x" * 40, "RATELIMIT_STORAGE_URI": "redis://cache:6379/0",
              "SESSION_COOKIE_SECURE": True, "DEBUG": False, "MENU_IMAGE_ALLOWED_HOSTS": (),
              "MAIL_BACKEND": "console"}
    problems = production_problems(config, "dev-only-change-me")
    assert any("MAIL_BACKEND" in problem for problem in problems)
