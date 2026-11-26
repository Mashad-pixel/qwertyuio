from datetime import timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models.user import User, UserRole
from app.models.user_session import UserSession
from app.security import totp
from app.services import session_service
from app.services.session_service import hash_token
from app.services.time_utils import utcnow
from tests.session_helpers import issue_test_session

PASSWORD = "StrongPass123!"


def _user(email, role, mfa_secret=None, mfa_enabled=False):
    user = User(name=email.split("@")[0], email=email, role=role, is_active=True)
    user.set_password(PASSWORD)
    user.mfa_secret = mfa_secret
    user.mfa_enabled = mfa_enabled
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _session_client(app, user, mfa_verified=True):
    """A client holding a real server-side session for the user. Returns (client, token)."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        token = issue_test_session(user, mfa_verified=mfa_verified)
        sess["sid"] = token
    return client, token


def _wrong_code(secret):
    counter = totp.current_counter()
    valid = {totp.code_at(secret, step) for step in (counter - 1, counter, counter + 1)}
    return next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in valid)


# ---------- Production startup ----------

def test_missing_flask_config_starts_production_and_refuses_unsafe_settings():
    # The default is production. The test environment has no production secrets, so startup
    # must be refused rather than silently running development settings.
    with pytest.raises(RuntimeError, match="unsafe production configuration"):
        create_app()


# ---------- Administrator MFA ----------

def test_admin_without_mfa_can_only_sign_in_and_enroll(app):
    _user("admin-setup@test.com", UserRole.ADMIN)
    client = app.test_client()

    response = _login(client, "admin-setup@test.com")
    assert response.status_code == 200
    assert response.get_json()["data"]["mfa_setup_required"] is True

    blocked = client.get("/api/admin/menu")
    assert blocked.status_code == 403
    assert blocked.get_json()["error"]["code"] == "MFA_REQUIRED"

    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/menu").status_code == 200


def test_admin_enrolls_a_second_factor_and_gains_access(app):
    _user("admin-enroll@test.com", UserRole.ADMIN)
    client = app.test_client()
    _login(client, "admin-enroll@test.com")

    setup = client.post("/api/auth/mfa/setup", json={})
    assert setup.status_code == 200
    data = setup.get_json()["data"]
    assert data["otpauth_uri"].startswith("otpauth://totp/")

    wrong = client.post("/api/auth/mfa/confirm", json={"code": _wrong_code(data["secret"])})
    assert wrong.status_code == 400
    assert wrong.get_json()["error"]["code"] == "INVALID_MFA_CODE"

    confirm = client.post(
        "/api/auth/mfa/confirm",
        json={"code": totp.code_at(data["secret"], totp.current_counter())},
    )
    assert confirm.status_code == 200
    assert client.get("/api/admin/menu").status_code == 200
    assert client.post("/api/auth/mfa/setup", json={}).status_code == 409


def test_admin_with_mfa_gets_no_session_until_the_code_is_accepted(app):
    secret = totp.generate_secret()
    _user("admin-mfa@test.com", UserRole.ADMIN, mfa_secret=secret, mfa_enabled=True)
    client = app.test_client()

    response = _login(client, "admin-mfa@test.com")
    assert response.get_json()["data"]["mfa_required"] is True
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/admin/menu").status_code == 401

    wrong = client.post("/api/auth/mfa/verify", json={"code": _wrong_code(secret)})
    assert wrong.status_code == 400

    right = client.post("/api/auth/mfa/verify", json={"code": totp.code_at(secret, totp.current_counter())})
    assert right.status_code == 200
    assert client.get("/api/admin/menu").status_code == 200


def test_used_authenticator_code_cannot_be_replayed(app):
    secret = totp.generate_secret()
    _user("admin-replay@test.com", UserRole.ADMIN, mfa_secret=secret, mfa_enabled=True)
    code = totp.code_at(secret, totp.current_counter())

    first = app.test_client()
    _login(first, "admin-replay@test.com")
    assert first.post("/api/auth/mfa/verify", json={"code": code}).status_code == 200

    second = app.test_client()
    _login(second, "admin-replay@test.com")
    replay = second.post("/api/auth/mfa/verify", json={"code": code})
    assert replay.status_code == 400


def test_repeated_wrong_codes_lock_the_account(app):
    secret = totp.generate_secret()
    _user("admin-lock@test.com", UserRole.ADMIN, mfa_secret=secret, mfa_enabled=True)
    client = app.test_client()
    _login(client, "admin-lock@test.com")

    for _ in range(app.config["MFA_MAX_FAILED_ATTEMPTS"]):
        assert client.post("/api/auth/mfa/verify", json={"code": _wrong_code(secret)}).status_code == 400

    locked = client.post("/api/auth/mfa/verify", json={"code": totp.code_at(secret, totp.current_counter())})
    assert locked.status_code == 429
    assert locked.get_json()["error"]["code"] == "MFA_LOCKED"


def test_password_step_expires_if_the_code_is_not_entered_in_time(app):
    secret = totp.generate_secret()
    _user("admin-expire@test.com", UserRole.ADMIN, mfa_secret=secret, mfa_enabled=True)
    client = app.test_client()
    _login(client, "admin-expire@test.com")

    with client.session_transaction() as sess:
        pending = dict(sess["mfa_pending"])
        pending["since"] = (utcnow() - timedelta(minutes=app.config["MFA_PENDING_MINUTES"] + 1)).isoformat()
        sess["mfa_pending"] = pending

    response = client.post("/api/auth/mfa/verify", json={"code": totp.code_at(secret, totp.current_counter())})
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "MFA_SESSION_EXPIRED"


def test_unverified_admin_session_cannot_reach_admin_features(app):
    admin = _user("admin-unverified@test.com", UserRole.ADMIN)
    client, _ = _session_client(app, admin, mfa_verified=False)
    response = client.get("/api/admin/menu")
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "MFA_REQUIRED"


# ---------- Server-side sessions ----------

def test_logout_revokes_the_server_session_so_a_copied_cookie_stops_working(app):
    student = _user("logout@test.com", UserRole.STUDENT)
    client = app.test_client()
    _login(client, "logout@test.com")
    with client.session_transaction() as sess:
        token = sess["sid"]

    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout", json={}).status_code == 200

    replay = app.test_client()
    with replay.session_transaction() as sess:
        sess["_user_id"] = str(student.id)
        sess["_fresh"] = True
        sess["sid"] = token
    assert replay.get("/api/auth/me").status_code == 401
    assert db.session.get(UserSession, hash_token(token)).revoked_at is not None


def test_privileged_session_expires_after_its_idle_limit(app):
    admin = _user("idle-admin@test.com", UserRole.ADMIN)
    client, token = _session_client(app, admin)
    assert client.get("/api/admin/menu").status_code == 200

    row = db.session.get(UserSession, hash_token(token))
    row.last_seen_at = utcnow() - timedelta(minutes=app.config["SESSION_IDLE_MINUTES_PRIVILEGED"] + 5)
    db.session.commit()

    assert client.get("/api/auth/me").status_code == 401
    assert db.session.get(UserSession, hash_token(token)).revoked_at is not None


def test_privileged_session_expires_at_its_absolute_limit(app):
    admin = _user("absolute-admin@test.com", UserRole.ADMIN)
    client, token = _session_client(app, admin)

    row = db.session.get(UserSession, hash_token(token))
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()

    assert client.get("/api/auth/me").status_code == 401


def test_cookie_without_a_server_session_is_rejected(app):
    student = _user("bare-cookie@test.com", UserRole.STUDENT)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(student.id)
        sess["_fresh"] = True
    assert client.get("/api/auth/me").status_code == 401


def test_revoking_a_user_ends_every_device(app):
    student = _user("every-device@test.com", UserRole.STUDENT)
    laptop, _ = _session_client(app, student)
    phone, _ = _session_client(app, student)
    assert laptop.get("/api/auth/me").status_code == 200

    assert session_service.revoke_user_sessions(student.id) == 2
    assert laptop.get("/api/auth/me").status_code == 401
    assert phone.get("/api/auth/me").status_code == 401


# ---------- Menu image policy through the admin API ----------

def _admin_menu_client(app):
    admin = _user("image-admin@test.com", UserRole.ADMIN)
    client, _ = _session_client(app, admin)
    return client


def _menu_payload(image_url):
    return {"name": "Test Dish", "category": "Snacks", "price_paise": 5000, "image_url": image_url}


@pytest.mark.parametrize(
    "image_url",
    [
        "http://images.unsplash.com/photo-1.jpg",
        "https://evil.example.com/photo-1.jpg",
        "https://evil.com@images.unsplash.com/photo-1.jpg",
        "javascript:alert(1)",
    ],
)
def test_menu_image_must_be_https_on_an_approved_host(app, image_url):
    client = _admin_menu_client(app)
    response = client.post("/api/admin/menu", json=_menu_payload(image_url))
    assert response.status_code == 400
    assert "image_url" in response.get_json()["details"]


def test_menu_image_on_an_approved_https_host_is_accepted(app):
    client = _admin_menu_client(app)
    response = client.post(
        "/api/admin/menu",
        json=_menu_payload("https://images.unsplash.com/photo-1.jpg?auto=format&w=900"),
    )
    assert response.status_code == 201


# ---------- Headers ----------

def test_html_pages_are_served_with_a_policy_that_forbids_inline_script(app):
    response = app.test_client().get("/frontend/index.html")
    policy = response.headers["Content-Security-Policy"]
    script_src = next(part for part in policy.split(";") if part.strip().startswith("script-src"))
    assert "'unsafe-inline'" not in script_src
    assert "frame-ancestors 'none'" in policy


def test_api_responses_get_a_locked_down_policy(app):
    response = app.test_client().get("/api/health")
    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")
