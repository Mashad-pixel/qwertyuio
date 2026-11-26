"""Staff accounts (admin-managed) and the canteen open/closed switch."""
import pytest

from app.extensions import db
from app.models.user import User, UserRole
from tests.session_helpers import issue_test_session


def make_user(email, role, name="Person", password="StrongPass123!"):
    user = User(name=name, email=email, role=role, is_active=True)
    user.set_password(password)
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


@pytest.fixture
def admin(app):
    return make_user("admin@test.com", UserRole.ADMIN, name="Admin")


@pytest.fixture
def admin_client(app, admin):
    return signed_in(app, admin)


@pytest.fixture
def kitchen(app):
    return make_user("kitchen@test.com", UserRole.KITCHEN, name="Kitchen")


# ---------- Staff accounts ----------

def test_admin_lists_only_staff(admin_client, kitchen, student):
    staff = admin_client.get("/api/admin/staff").get_json()["data"]["staff"]
    emails = {row["email"] for row in staff}
    assert {"admin@test.com", "kitchen@test.com"} <= emails
    assert student.email not in emails
    assert all("password_hash" not in row and "mfa_secret" not in row for row in staff)


def test_kitchen_and_students_cannot_manage_staff(app, kitchen, student):
    kitchen_client = signed_in(app, kitchen)
    assert kitchen_client.get("/api/admin/staff").status_code == 403
    assert kitchen_client.post("/api/admin/staff", json={}).status_code == 403
    assert signed_in(app, student).get("/api/admin/staff").status_code == 403


def test_admin_creates_kitchen_staff_who_can_sign_in(admin_client, anon_client):
    created = admin_client.post("/api/admin/staff", json={
        "name": "  Ravi   Kumar ", "email": " Ravi@Canteen.EDU ",
        "password": "KitchenPass1", "role": "KITCHEN",
    })
    assert created.status_code == 201
    body = created.get_json()["data"]
    assert body["email"] == "ravi@canteen.edu"
    assert body["name"] == "Ravi Kumar"
    assert body["role"] == UserRole.KITCHEN

    login = anon_client.post("/api/auth/login", json={"email": "ravi@canteen.edu", "password": "KitchenPass1"})
    assert login.status_code == 200
    assert login.get_json()["data"]["role"] == UserRole.KITCHEN


def test_a_new_administrator_must_enrol_in_two_factor_before_admin_pages(admin_client, anon_client):
    admin_client.post("/api/admin/staff", json={
        "name": "New Admin", "email": "new.admin@test.com", "password": "AdminPass123", "role": "ADMIN",
    })
    login = anon_client.post("/api/auth/login", json={"email": "new.admin@test.com", "password": "AdminPass123"})
    assert login.status_code == 200
    assert login.get_json()["data"]["mfa_setup_required"] is True


@pytest.mark.parametrize("payload, code", [
    ({"name": "X", "email": "x@test.com", "password": "LongEnough1", "role": "STUDENT"}, "INVALID_ROLE"),
    ({"name": "X", "email": "x@test.com", "password": "onlyletters", "role": "KITCHEN"}, "INVALID_STAFF"),
    ({"name": "X", "email": "bad", "password": "LongEnough1", "role": "KITCHEN"}, "INVALID_STAFF"),
    ({"name": "X", "email": "x@test.com", "role": "KITCHEN"}, "INVALID_STAFF"),
])
def test_bad_staff_details_are_refused(admin_client, payload, code):
    response = admin_client.post("/api/admin/staff", json=payload)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == code


def test_duplicate_staff_email_is_refused(admin_client, kitchen):
    response = admin_client.post("/api/admin/staff", json={
        "name": "Dup", "email": "KITCHEN@test.com", "password": "LongEnough1", "role": "KITCHEN",
    })
    assert response.status_code == 409


def test_deactivating_staff_ends_their_sessions_immediately(app, admin_client, kitchen):
    kitchen_session = signed_in(app, kitchen)
    assert kitchen_session.get("/api/auth/me").status_code == 200

    response = admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"is_active": False})
    assert response.status_code == 200
    assert response.get_json()["data"]["is_active"] is False
    assert kitchen_session.get("/api/auth/me").status_code == 401


def test_changing_a_role_ends_the_old_sessions(app, admin_client, kitchen):
    kitchen_session = signed_in(app, kitchen)
    response = admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"role": "ADMIN"})
    assert response.status_code == 200
    assert response.get_json()["data"]["role"] == UserRole.ADMIN
    assert kitchen_session.get("/api/auth/me").status_code == 401


def test_setting_a_new_password_ends_sessions_and_the_old_password_stops_working(app, admin_client, kitchen, anon_client):
    kitchen_session = signed_in(app, kitchen)
    response = admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"password": "FreshPass2025"})
    assert response.status_code == 200
    assert kitchen_session.get("/api/auth/me").status_code == 401
    assert anon_client.post("/api/auth/login", json={"email": kitchen.email, "password": "StrongPass123!"}).status_code == 401
    assert anon_client.post("/api/auth/login", json={"email": kitchen.email, "password": "FreshPass2025"}).status_code == 200


def test_an_administrator_cannot_remove_their_own_access(admin_client, admin):
    demote = admin_client.patch(f"/api/admin/staff/{admin.id}", json={"role": "KITCHEN"})
    assert demote.status_code == 409
    assert demote.get_json()["error"]["code"] == "SELF_LOCKOUT"
    deactivate = admin_client.patch(f"/api/admin/staff/{admin.id}", json={"is_active": False})
    assert deactivate.status_code == 409
    rename = admin_client.patch(f"/api/admin/staff/{admin.id}", json={"name": "Chief Admin"})
    assert rename.status_code == 200


def test_staff_routes_never_touch_student_accounts(admin_client, student):
    response = admin_client.patch(f"/api/admin/staff/{student.id}", json={"is_active": False})
    assert response.status_code == 404
    assert db.session.get(User, student.id).is_active is True


def test_unknown_or_bad_staff_fields_are_refused(admin_client, kitchen):
    assert admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"password_hash": "x"}).status_code == 400
    assert admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"is_active": "no"}).status_code == 400
    assert admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={}).status_code == 400


# ---------- Canteen open/closed switch ----------

def test_closing_the_canteen_stops_orders_and_shows_the_admin_message(app, admin_client, client, menu):
    closed = admin_client.patch("/api/admin/canteen/status", json={
        "is_accepting_orders": False, "closed_message": "Closed for exams until Monday",
    })
    assert closed.status_code == 200
    assert closed.get_json() == {"is_accepting_orders": False, "message": "Closed for exams until Monday"}

    public = app.test_client().get("/api/canteen/status").get_json()
    assert public == {"is_accepting_orders": False, "message": "Closed for exams until Monday"}

    order = client.post("/api/orders", json={"items": [{"menu_item_id": menu["samosa"].id, "quantity": 1}]})
    assert order.status_code == 409
    body = order.get_json()
    assert body["error"]["code"] == "CANTEEN_CLOSED"
    assert body["message"] == "Closed for exams until Monday"


def test_reopening_the_canteen_allows_orders_again(app, admin_client, client, menu):
    admin_client.patch("/api/admin/canteen/status", json={"is_accepting_orders": False})
    admin_client.patch("/api/admin/canteen/status", json={"is_accepting_orders": True})
    assert app.test_client().get("/api/canteen/status").get_json()["is_accepting_orders"] is True
    order = client.post("/api/orders", json={"items": [{"menu_item_id": menu["samosa"].id, "quantity": 1}]})
    assert order.status_code == 201


def test_only_administrators_can_change_the_canteen_status(app, client, kitchen):
    assert client.patch("/api/admin/canteen/status", json={"is_accepting_orders": False}).status_code == 403
    assert signed_in(app, kitchen).patch("/api/admin/canteen/status", json={"is_accepting_orders": False}).status_code == 403
