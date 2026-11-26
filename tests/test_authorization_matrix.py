"""Negative authorization tests for every endpoint and every role.

Each row says who may call the endpoint:
  PUBLIC  anyone, including anonymous visitors
  AUTH    any logged-in user
  a set   only the listed roles

For every (endpoint, role) pair the test checks the denial is correct:
  anonymous user on a protected endpoint   -> 401 AUTH_REQUIRED
  logged-in user with the wrong role       -> 403 FORBIDDEN
  allowed role                              -> never 401 or 403

Requests use a nonexistent id (999999) and no body, so an allowed call fails validation
or lookup and changes nothing. Denied calls must be stopped before any work is done.

test_matrix_covers_every_registered_route is the guard: adding a route without adding a row here
fails the suite, so no new endpoint ships without an explicit access decision.
"""
import re

import pytest

from flask_login import login_required
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.user import User, UserRole
from app.security.permissions import roles_required

# Hashing once keeps the matrix fast. Every test still gets fresh rows.
_PASSWORD_HASH = generate_password_hash("StrongPass123!", method="scrypt")

ANON = "ANON"
PUBLIC = "PUBLIC"
AUTH = "AUTH"
KITCHEN_AND_ADMIN = frozenset({UserRole.KITCHEN, UserRole.ADMIN})
ADMIN_ONLY = frozenset({UserRole.ADMIN})
STUDENT_ONLY = frozenset({UserRole.STUDENT})
ROLES = [ANON, UserRole.STUDENT, UserRole.KITCHEN, UserRole.ADMIN]

# (method, rule template, policy)
MATRIX = [
    # Public
    ("GET", "/", PUBLIC),
    ("GET", "/frontend/", PUBLIC),
    ("GET", "/frontend/<path:filename>", PUBLIC),
    ("GET", "/static/<path:filename>", PUBLIC),
    ("GET", "/api/health", PUBLIC),
    ("GET", "/api/csrf-token", PUBLIC),
    ("GET", "/api/menu", PUBLIC),
    ("GET", "/api/menu/popular", PUBLIC),  # paid-unit counts only; no student or revenue data
    ("GET", "/api/canteen/status", PUBLIC),
    ("POST", "/api/auth/login", PUBLIC),
    ("POST", "/api/auth/register", PUBLIC),
    ("POST", "/api/payments/webhook", PUBLIC),  # protected by Razorpay's signature, not by login
    # Any logged-in user
    ("GET", "/api/auth/me", AUTH),
    ("POST", "/api/auth/logout", AUTH),
    # Students only
    ("GET", "/api/orders", STUDENT_ONLY),
    ("POST", "/api/orders", STUDENT_ONLY),
    ("GET", "/api/orders/<int:order_id>", STUDENT_ONLY),
    ("GET", "/api/orders/<int:order_id>/tracking", STUDENT_ONLY),
    ("GET", "/api/orders/<int:order_id>/collection-qr", STUDENT_ONLY),
    ("POST", "/api/payments/create-order", STUDENT_ONLY),
    ("POST", "/api/payments/verify", STUDENT_ONLY),
    # Kitchen staff and admins
    ("GET", "/api/kitchen/orders", KITCHEN_AND_ADMIN),
    ("PATCH", "/api/kitchen/orders/<int:order_id>/status", KITCHEN_AND_ADMIN),
    ("POST", "/api/kitchen/collection/verify", KITCHEN_AND_ADMIN),
    ("POST", "/api/kitchen/collection/confirm", KITCHEN_AND_ADMIN),
    # Admins only
    ("GET", "/api/admin/staff", ADMIN_ONLY),
    ("POST", "/api/admin/staff", ADMIN_ONLY),
    ("PATCH", "/api/admin/staff/<int:user_id>", ADMIN_ONLY),
    ("GET", "/api/admin/menu", ADMIN_ONLY),
    ("POST", "/api/admin/menu", ADMIN_ONLY),
    ("PATCH", "/api/admin/menu/<int:item_id>", ADMIN_ONLY),
    ("PATCH", "/api/admin/canteen/status", ADMIN_ONLY),
    ("GET", "/api/admin/firebase/status", ADMIN_ONLY),
    ("GET", "/api/admin/orders", ADMIN_ONLY),
    ("GET", "/api/admin/orders/<int:order_id>", ADMIN_ONLY),
    ("POST", "/api/admin/orders/<int:order_id>/cancel", ADMIN_ONLY),
    ("POST", "/api/admin/payments/<int:payment_id>/refund", ADMIN_ONLY),
    ("GET", "/api/admin/payments/<int:payment_id>/refunds", ADMIN_ONLY),
    ("GET", "/api/admin/reports/overview", ADMIN_ONLY),
    ("GET", "/api/admin/reports/sales", ADMIN_ONLY),
    ("GET", "/api/admin/reports/popular-items", ADMIN_ONLY),
    ("GET", "/api/admin/reports/categories", ADMIN_ONLY),
    ("GET", "/api/admin/reports/peak-hours", ADMIN_ONLY),
    ("GET", "/api/admin/reports/orders", ADMIN_ONLY),
]

MATRIX_KEYS = {(method, rule) for method, rule, _ in MATRIX}
assert len(MATRIX_KEYS) == len(MATRIX), "duplicate matrix row"


def _concrete_path(rule):
    """Fill route parameters with a nonexistent id, or a harmless filename for static paths."""
    path = re.sub(r"<int:[a-z_]+>", "999999", rule)
    return path.replace("<path:filename>", "index.html")


def _allowed(policy, role):
    if policy == PUBLIC:
        return True
    if policy == AUTH:
        return role != ANON
    return role in policy


@pytest.fixture
def people(app):
    """One account per role. Distinct emails, so these fixtures never clash with conftest's student."""
    created = {}
    for role, email in [
        (UserRole.STUDENT, "matrix-student@test.com"),
        (UserRole.KITCHEN, "matrix-kitchen@test.com"),
        (UserRole.ADMIN, "matrix-admin@test.com"),
    ]:
        user = User(name=role.title(), email=email, role=role, is_active=True)
        user.password_hash = _PASSWORD_HASH
        db.session.add(user)
        db.session.commit()
        created[role] = user.id
    return created


def _client_for(app, people, role):
    client = app.test_client()
    if role != ANON:
        with client.session_transaction() as sess:
            sess["_user_id"] = str(people[role])
            sess["_fresh"] = True
    return client


def _send(client, method, path):
    # No body: an allowed call then fails validation before touching any data.
    return client.open(path, method=method)


CASES = [
    pytest.param(method, rule, policy, role, id=f"{method} {rule} as {role}")
    for method, rule, policy in MATRIX
    for role in ROLES
]


@pytest.mark.parametrize("method, rule, policy, role", CASES)
def test_endpoint_enforces_its_access_policy(app, people, method, rule, policy, role):
    response = _send(_client_for(app, people, role), method, _concrete_path(rule))

    if policy == PUBLIC:
        assert response.status_code not in (401, 403)
    elif _allowed(policy, role):
        assert response.status_code not in (401, 403), response.get_data(as_text=True)[:200]
    elif role == ANON:
        assert response.status_code == 401
        assert response.get_json()["error"]["code"] == "AUTH_REQUIRED"
    else:
        assert response.status_code == 403
        assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_matrix_covers_every_registered_route(app):
    registered = set()
    for rule in app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            registered.add((method, rule.rule))

    missing = sorted(registered - MATRIX_KEYS)
    stale = sorted(MATRIX_KEYS - registered)

    assert missing == [], f"routes without an access decision in the matrix: {missing}"
    assert stale == [], f"matrix rows for routes that no longer exist: {stale}"


def test_anonymous_access_to_roles_required_route_is_401_not_500(app, anon_client):
    """Regression guard: roles_required used to crash for anonymous users if login_required was missing."""

    @app.get("/api/_probe_roles_only")
    @roles_required(UserRole.ADMIN)
    def probe():
        return {"ok": True}

    response = anon_client.get("/api/_probe_roles_only")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTH_REQUIRED"


def test_login_required_plus_roles_required_still_denies_wrong_role(app, people):
    @app.get("/api/_probe_student_only")
    @login_required
    @roles_required(UserRole.STUDENT)
    def probe():
        return {"ok": True}

    response = _client_for(app, people, UserRole.ADMIN).get("/api/_probe_student_only")

    assert response.status_code == 403


def test_roles_required_rejects_empty_role_list_at_definition_time():
    with pytest.raises(ValueError):
        roles_required()


def test_denied_requests_change_nothing(app, people):
    """A student calling an admin write endpoint must not create a menu item."""
    from app.models.menu import MenuItem

    before = MenuItem.query.count()
    response = _send(_client_for(app, people, UserRole.STUDENT), "POST", "/api/admin/menu")

    assert response.status_code == 403
    assert MenuItem.query.count() == before
