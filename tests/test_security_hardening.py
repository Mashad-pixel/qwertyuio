from tests.session_helpers import issue_test_session
from app.extensions import db
from app.models.user import User


def _login_as(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True
        session["sid"] = issue_test_session(user)


def test_security_headers_are_present(client):
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" in response.headers["Permissions-Policy"]
    assert response.headers["Cache-Control"] == "no-store"
    assert "Cookie" in response.headers.get("Vary", "")


def test_hsts_is_only_emitted_for_secure_requests(client):
    insecure = client.get("/api/health", base_url="http://localhost")
    secure = client.get("/api/health", base_url="https://localhost")
    assert "Strict-Transport-Security" not in insecure.headers
    assert secure.headers["Strict-Transport-Security"] == "max-age=31536000"


def test_admin_cannot_access_student_order_endpoints(app):
    admin = User(name="Admin User", email="audit-admin@test.com", role="ADMIN", is_active=True)
    admin.set_password("StrongPass123!")
    db.session.add(admin)
    db.session.commit()

    client = app.test_client()
    _login_as(client, admin)
    endpoints = [
        "/api/orders",
        "/api/orders/1",
        "/api/orders/1/tracking",
        "/api/orders/1/collection-qr",
    ]
    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 403, (endpoint, response.get_json())
        assert response.get_json()["error"]["code"] == "FORBIDDEN"


def test_kitchen_cannot_access_student_order_endpoints(app):
    kitchen = User(name="Kitchen User", email="audit-kitchen@test.com", role="KITCHEN", is_active=True)
    kitchen.set_password("StrongPass123!")
    db.session.add(kitchen)
    db.session.commit()

    client = app.test_client()
    _login_as(client, kitchen)
    endpoints = [
        "/api/orders",
        "/api/orders/1",
        "/api/orders/1/tracking",
        "/api/orders/1/collection-qr",
    ]
    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 403, (endpoint, response.get_json())
        assert response.get_json()["error"]["code"] == "FORBIDDEN"
