from tests.session_helpers import issue_test_session
import pytest

from app.extensions import db
from app.models.menu import MenuItem
from app.models.user import User, UserRole


def _client_for_role(app, role, email):
    user = User(name=role.title(), email=email, role=role, is_active=True)
    user.set_password("StrongPass123!")
    db.session.add(user)
    db.session.commit()
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True
        session["sid"] = issue_test_session(user)
    return client


@pytest.fixture
def admin_client(app):
    return _client_for_role(app, UserRole.ADMIN, "foundation-admin@test.com")


@pytest.fixture
def kitchen_client(app):
    return _client_for_role(app, UserRole.KITCHEN, "foundation-kitchen@test.com")


def test_health_endpoint_reports_database_status(app):
    response = app.test_client().get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": "ok"}


def test_canteen_defaults_to_open_and_admin_can_close_and_reopen(app, admin_client):
    client = app.test_client()
    assert client.get("/api/canteen/status").get_json() == {
        "is_accepting_orders": True,
        "message": None,
    }

    closed = admin_client.patch(
        "/api/admin/canteen/status",
        json={"is_accepting_orders": False, "closed_message": "Closed for maintenance"},
    )
    assert closed.status_code == 200
    assert client.get("/api/canteen/status").get_json() == {
        "is_accepting_orders": False,
        "message": "Closed for maintenance",
    }

    reopened = admin_client.patch(
        "/api/admin/canteen/status",
        json={"is_accepting_orders": True},
    )
    assert reopened.status_code == 200
    assert client.get("/api/canteen/status").get_json() == {
        "is_accepting_orders": True,
        "message": None,
    }


def test_order_creation_is_blocked_when_canteen_is_closed(app, admin_client, client, menu):
    admin_client.patch(
        "/api/admin/canteen/status",
        json={"is_accepting_orders": False},
    )
    response = client.post(
        "/api/orders",
        json={"items": [{"menu_item_id": menu["tea"].id, "quantity": 1}]},
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "CANTEEN_CLOSED"


def test_public_menu_hides_unavailable_sold_out_and_reserved_stock(app, menu):
    paneer = menu["paneer_roll"]
    paneer.reserved_quantity = 1
    sold_out = MenuItem(
        name="Sold out", category="Meals", price_paise=2000,
        is_available=True, stock_quantity=0,
    )
    hidden = MenuItem(
        name="Hidden", category="Meals", price_paise=2000,
        is_available=False, stock_quantity=None,
    )
    db.session.add_all([sold_out, hidden])
    db.session.commit()

    response = app.test_client().get("/api/menu")
    assert response.status_code == 200
    items = response.get_json()["items"]
    names = [item["name"] for item in items]
    assert "Tea" in names
    assert "Paneer Roll" in names
    assert "Sold out" not in names
    assert "Hidden" not in names
    assert all("stock_quantity" not in item and "reserved_quantity" not in item for item in items)


def test_admin_can_create_and_update_menu_items(admin_client):
    payload = {
        "name": "Veg Biryani",
        "category": "Meals",
        "price_paise": 12000,
        "stock_quantity": 10,
    }
    created = admin_client.post("/api/admin/menu", json=payload)
    assert created.status_code == 201
    item_id = created.get_json()["item"]["id"]

    updated = admin_client.patch(
        f"/api/admin/menu/{item_id}",
        json={"price_paise": 13000, "is_available": False},
    )
    assert updated.status_code == 200
    item = updated.get_json()["item"]
    assert item["price_paise"] == 13000
    assert item["is_available"] is False


def test_menu_admin_rejects_stock_below_existing_reservations(admin_client, menu):
    item = menu["paneer_roll"]
    item.reserved_quantity = 1
    db.session.commit()

    response = admin_client.patch(
        f"/api/admin/menu/{item.id}",
        json={"stock_quantity": 0},
    )
    assert response.status_code == 400
    assert "stock_quantity" in response.get_json()["details"]


def test_menu_admin_and_canteen_controls_are_admin_only(anon_client, kitchen_client):
    assert anon_client.get("/api/admin/menu").status_code == 401
    assert anon_client.post("/api/admin/menu", json={}).status_code == 401
    assert kitchen_client.get("/api/admin/menu").status_code == 403
    assert kitchen_client.post(
        "/api/admin/menu",
        json={"name": "Tea", "category": "Drinks", "price_paise": 1000},
    ).status_code == 403


def test_state_changing_requests_require_csrf_token(app, client, menu):
    app.config["WTF_CSRF_ENABLED"] = True
    payload = {"items": [{"menu_item_id": menu["tea"].id, "quantity": 1}]}

    rejected = client.post("/api/orders", json=payload)
    assert rejected.status_code == 400
    assert rejected.get_json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    token = client.get("/api/csrf-token").get_json()["csrf_token"]
    accepted = client.post(
        "/api/orders",
        json=payload,
        headers={"X-CSRFToken": token},
    )
    assert accepted.status_code == 201


def test_razorpay_webhook_is_exempt_from_browser_csrf_checks(app):
    app.config["WTF_CSRF_ENABLED"] = True
    response = app.test_client().post(
        "/api/payments/webhook",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    # The webhook rejects a missing/bad Razorpay signature, not a missing browser CSRF token.
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_SIGNATURE"


def test_api_responses_include_security_headers(app):
    response = app.test_client().get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
