import pytest

from app.extensions import db
from app.models.user import User, UserRole

PASSWORD = "StaffPass123"


def make_user(email, role, name=None, active=True, password=PASSWORD):
    user = User(name=name or email.split("@")[0].title(), email=email, role=role, is_active=active)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def client_for(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return client


@pytest.fixture
def admin(app):
    return make_user("admin@test.com", UserRole.ADMIN, name="Admin One")


@pytest.fixture
def admin_client(app, admin):
    return client_for(app, admin)


@pytest.fixture
def kitchen(app):
    return make_user("kitchen@test.com", UserRole.KITCHEN, name="Kitchen One")


@pytest.fixture
def student_user(app):
    return make_user("student@test.com", UserRole.STUDENT, name="Student One")


def test_list_returns_only_staff_accounts(app, admin_client, kitchen, student_user):
    response = admin_client.get("/api/admin/staff")
    assert response.status_code == 200
    emails = {row["email"] for row in response.get_json()["data"]["staff"]}
    assert emails == {"admin@test.com", "kitchen@test.com"}


def test_admin_creates_kitchen_account_that_can_log_in(app, admin_client):
    response = admin_client.post("/api/admin/staff", json={
        "name": "New Cook",
        "email": "Cook@Canteen.edu",
        "role": "KITCHEN",
        "password": "CookPass123",
    })
    assert response.status_code == 201
    created = response.get_json()["data"]
    assert created["email"] == "cook@canteen.edu"
    assert created["role"] == "KITCHEN"
    assert created["is_active"] is True
    assert "password" not in created and "password_hash" not in created

    login = app.test_client().post("/api/auth/login", json={
        "email": "cook@canteen.edu",
        "password": "CookPass123",
    })
    assert login.status_code == 200
    assert login.get_json()["data"]["role"] == "KITCHEN"


def test_create_rejects_student_role_and_weak_password(admin_client):
    student_role = admin_client.post("/api/admin/staff", json={
        "name": "Sneaky", "email": "sneaky@test.com", "role": "STUDENT", "password": "CookPass123",
    })
    assert student_role.status_code == 400
    assert student_role.get_json()["error"]["code"] == "INVALID_ROLE"

    weak = admin_client.post("/api/admin/staff", json={
        "name": "Weak", "email": "weak@test.com", "role": "KITCHEN", "password": "short",
    })
    assert weak.status_code == 400
    assert weak.get_json()["error"]["code"] == "INVALID_STAFF"


def test_create_rejects_duplicate_email(admin_client, kitchen):
    response = admin_client.post("/api/admin/staff", json={
        "name": "Dup", "email": "kitchen@test.com", "role": "KITCHEN", "password": "CookPass123",
    })
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "EMAIL_UNAVAILABLE"


def test_staff_api_cannot_create_or_edit_students(admin_client, student_user):
    response = admin_client.patch(f"/api/admin/staff/{student_user.id}", json={"is_active": False})
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "STAFF_NOT_FOUND"
    db.session.refresh(student_user)
    assert student_user.is_active is True


def test_admin_can_change_kitchen_role_and_deactivation_blocks_login(app, admin_client, kitchen):
    promoted = admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"role": "ADMIN"})
    assert promoted.status_code == 200
    assert promoted.get_json()["data"]["role"] == "ADMIN"

    deactivated = admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"is_active": False})
    assert deactivated.status_code == 200
    assert deactivated.get_json()["data"]["is_active"] is False

    login = app.test_client().post("/api/auth/login", json={
        "email": "kitchen@test.com", "password": PASSWORD,
    })
    assert login.status_code == 401


def test_admin_cannot_demote_or_disable_themselves(admin_client, admin):
    demote = admin_client.patch(f"/api/admin/staff/{admin.id}", json={"role": "KITCHEN"})
    assert demote.status_code == 409
    assert demote.get_json()["error"]["code"] == "SELF_LOCKOUT"

    disable = admin_client.patch(f"/api/admin/staff/{admin.id}", json={"is_active": False})
    assert disable.status_code == 409
    db.session.refresh(admin)
    assert admin.role == UserRole.ADMIN and admin.is_active is True


def test_admin_can_disable_another_admin(admin_client):
    other = make_user("other-admin@test.com", UserRole.ADMIN, name="Other Admin")
    response = admin_client.patch(f"/api/admin/staff/{other.id}", json={"is_active": False})
    assert response.status_code == 200
    db.session.refresh(other)
    assert other.is_active is False


def test_admin_can_reset_staff_password(app, admin_client, kitchen):
    response = admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"password": "NewCook456"})
    assert response.status_code == 200

    old = app.test_client().post("/api/auth/login", json={"email": "kitchen@test.com", "password": PASSWORD})
    new = app.test_client().post("/api/auth/login", json={"email": "kitchen@test.com", "password": "NewCook456"})
    assert old.status_code == 401
    assert new.status_code == 200


def test_patch_rejects_unknown_fields_and_bad_values(admin_client, kitchen):
    unknown = admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"email": "x@test.com"})
    assert unknown.status_code == 400

    empty = admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={})
    assert empty.status_code == 400

    bad_flag = admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"is_active": "no"})
    assert bad_flag.status_code == 400


def test_non_admins_are_refused(app, kitchen, student_user):
    anon = app.test_client()
    assert anon.get("/api/admin/staff").status_code == 401
    assert client_for(app, kitchen).get("/api/admin/staff").status_code == 403
    assert client_for(app, student_user).post("/api/admin/staff", json={}).status_code == 403
