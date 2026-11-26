"""Integration tests for the administrator panel: setup, account security, categories, canteen details.

Uses the shared pytest fixtures in conftest.py (`app`, `anon_client`, `client`). Requires the project's
dependencies (Flask, Flask-SQLAlchemy, pytest), which are listed in requirements.txt.
"""

import json
from pathlib import Path

import pytest

from app.extensions import db
from app.models.canteen import CanteenSettings
from app.models.menu import MenuItem
from app.models.menu_category import MenuCategory
from app.models.user import User, UserRole
from app.models.user_session import UserSession
from app.routes.auth import _login_account_key
from app.services.session_service import hash_token
from tests.session_helpers import issue_test_session

PASSWORD = "OwnerPass123!"
NEW_PASSWORD = "NewOwnerPass456!"
SEED_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "menu_seed.json"


def make_user(email, role, password=PASSWORD, name="Test User", active=True):
    user = User(name=name, email=email, role=role, is_active=active)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def login_as(app, user, mfa_verified=True):
    """A client whose browser holds a real server-side session row, as a completed sign-in would."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["sid"] = issue_test_session(user, mfa_verified=mfa_verified)
    return client


def session_row_for(token):
    db.session.expire_all()
    return db.session.get(UserSession, hash_token(token))


@pytest.fixture
def owner(app):
    return make_user("owner@test.com", UserRole.ADMIN, name="Owner")


@pytest.fixture
def owner_client(app, owner):
    return login_as(app, owner)


@pytest.fixture
def kitchen(app):
    return make_user("kitchen@test.com", UserRole.KITCHEN, name="Kitchen")


@pytest.fixture
def kitchen_client(app, kitchen):
    return login_as(app, kitchen)


# ---------- First-run setup and operator reset (CLI) ----------

def test_setup_admin_creates_the_first_administrator_with_a_hashed_password(app):
    result = app.test_cli_runner().invoke(
        args=["setup-admin", "--email", "Boss@Example.com", "--name", "Canteen Boss"],
        input="Sup3rSecret!\nSup3rSecret!\n",
    )
    assert result.exit_code == 0, result.output
    admin = User.query.filter_by(role=UserRole.ADMIN).one()
    assert admin.email == "boss@example.com"
    assert admin.name == "Canteen Boss"
    assert admin.check_password("Sup3rSecret!")
    assert admin.password_hash != "Sup3rSecret!"
    assert admin.password_hash.startswith("scrypt:")


def test_setup_admin_refuses_once_an_administrator_exists(app, owner):
    result = app.test_cli_runner().invoke(
        args=["setup-admin", "--email", "second@test.com"],
        input="Sup3rSecret!\nSup3rSecret!\n",
    )
    assert result.exit_code != 0
    assert "already exists" in result.output
    assert User.query.filter_by(email="second@test.com").first() is None


def test_setup_admin_rejects_a_weak_password_and_creates_nothing(app):
    result = app.test_cli_runner().invoke(
        args=["setup-admin", "--email", "boss@test.com"],
        input="short\nshort\n",
    )
    assert result.exit_code != 0
    assert User.query.count() == 0


def test_setup_admin_rejects_mismatched_password_confirmation(app):
    result = app.test_cli_runner().invoke(
        args=["setup-admin", "--email", "boss@test.com"],
        input="Sup3rSecret!\nDifferent123!\n",
    )
    assert result.exit_code != 0
    assert User.query.count() == 0


def test_reset_admin_credentials_changes_email_and_password_and_ends_sessions(app, owner):
    token = issue_test_session(owner)
    result = app.test_cli_runner().invoke(
        args=["reset-admin-credentials", "--current-email", "owner@test.com", "--new-email", "new-owner@test.com"],
        input=f"{NEW_PASSWORD}\n{NEW_PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    db.session.refresh(owner)
    assert owner.email == "new-owner@test.com"
    assert owner.check_password(NEW_PASSWORD)
    assert owner.check_password(PASSWORD) is False
    assert session_row_for(token).revoked_at is not None


def test_reset_admin_credentials_only_applies_to_administrators(app, kitchen):
    result = app.test_cli_runner().invoke(
        args=["reset-admin-credentials", "--current-email", "kitchen@test.com"],
        input=f"{NEW_PASSWORD}\n{NEW_PASSWORD}\n",
    )
    assert result.exit_code != 0
    assert "not an administrator" in result.output


def test_seed_menu_creates_every_category_before_its_items(app):
    entries = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    result = app.test_cli_runner().invoke(args=["seed-menu"])
    assert result.exit_code == 0, result.output
    names = {row.name for row in MenuCategory.query.all()}
    assert names == {entry["category"] for entry in entries}
    assert MenuItem.query.count() == len(entries)


# ---------- Account: password, email, sessions ----------

def test_account_profile_reports_role_and_two_factor_state(owner_client):
    body = owner_client.get("/api/account").get_json()
    assert body["success"] is True
    assert body["data"]["email"] == "owner@test.com"
    assert body["data"]["role"] == UserRole.ADMIN
    assert body["data"]["mfa_enabled"] is False


def test_account_routes_require_sign_in(anon_client):
    assert anon_client.get("/api/account").status_code == 401
    assert anon_client.post("/api/account/password", json={}).status_code == 401
    assert anon_client.post("/api/account/email", json={}).status_code == 401


def test_administrator_without_second_factor_cannot_use_account_routes(app, owner):
    locked = login_as(app, owner, mfa_verified=False)
    response = locked.get("/api/account")
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "MFA_REQUIRED"


def test_password_change_rejects_a_wrong_current_password(owner_client, owner):
    response = owner_client.post("/api/account/password", json={
        "current_password": "not-my-password", "new_password": NEW_PASSWORD,
    })
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "CURRENT_PASSWORD_INCORRECT"
    db.session.refresh(owner)
    assert owner.check_password(PASSWORD)


@pytest.mark.parametrize("new_password, code", [
    ("short1", "INVALID_PASSWORD"),
    ("lettersonly", "INVALID_PASSWORD"),
    (PASSWORD, "PASSWORD_UNCHANGED"),
])
def test_password_change_validates_the_new_password(owner_client, new_password, code):
    response = owner_client.post("/api/account/password", json={
        "current_password": PASSWORD, "new_password": new_password,
    })
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == code


def test_password_change_needs_text_values(owner_client):
    response = owner_client.post("/api/account/password", json={"current_password": 1, "new_password": None})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "MISSING_FIELDS"


def test_password_change_signs_out_other_sessions_but_keeps_this_one(app, owner, owner_client):
    other_token = issue_test_session(owner)
    response = owner_client.post("/api/account/password", json={
        "current_password": PASSWORD, "new_password": NEW_PASSWORD,
    })
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["signed_out_other_sessions"] == 1

    db.session.refresh(owner)
    assert owner.check_password(NEW_PASSWORD)
    assert owner.check_password(PASSWORD) is False
    assert owner.password_changed_at is not None
    assert session_row_for(other_token).revoked_at is not None
    assert owner_client.get("/api/account").status_code == 200


def test_email_change_rejects_a_wrong_password_and_a_taken_address(app, owner, owner_client):
    make_user("taken@test.com", UserRole.STUDENT)
    wrong = owner_client.post("/api/account/email", json={"current_password": "nope", "new_email": "fresh@test.com"})
    assert wrong.status_code == 400
    assert wrong.get_json()["error"]["code"] == "CURRENT_PASSWORD_INCORRECT"

    taken = owner_client.post("/api/account/email", json={"current_password": PASSWORD, "new_email": "TAKEN@test.com"})
    assert taken.status_code == 409
    assert taken.get_json()["error"]["code"] == "EMAIL_UNAVAILABLE"

    invalid = owner_client.post("/api/account/email", json={"current_password": PASSWORD, "new_email": "not-an-email"})
    assert invalid.status_code == 400
    assert invalid.get_json()["error"]["code"] == "INVALID_EMAIL"

    same = owner_client.post("/api/account/email", json={"current_password": PASSWORD, "new_email": "OWNER@test.com"})
    assert same.get_json()["error"]["code"] == "EMAIL_UNCHANGED"


def test_email_change_updates_the_address_and_normalises_it(owner_client, owner):
    response = owner_client.post("/api/account/email", json={
        "current_password": PASSWORD, "new_email": "  Canteen.Admin@Example.COM ",
    })
    assert response.status_code == 200
    assert response.get_json()["data"]["email"] == "canteen.admin@example.com"
    db.session.refresh(owner)
    assert owner.email == "canteen.admin@example.com"


def test_sessions_list_marks_this_browser_and_revoke_leaves_it_signed_in(app, owner, owner_client):
    issue_test_session(owner)
    issue_test_session(owner)
    listed = owner_client.get("/api/account/sessions").get_json()["data"]["sessions"]
    assert len(listed) == 3
    assert sum(1 for s in listed if s["current"]) == 1

    revoked = owner_client.post("/api/account/sessions/revoke-others").get_json()["data"]["revoked"]
    assert revoked == 2
    remaining = owner_client.get("/api/account/sessions").get_json()["data"]["sessions"]
    assert len(remaining) == 1 and remaining[0]["current"] is True


def test_login_throttle_key_is_per_normalised_email(app):
    with app.test_request_context("/api/auth/login", method="POST", json={"email": " Owner@Test.com "}):
        first = _login_account_key()
    with app.test_request_context("/api/auth/login", method="POST", json={"email": "owner@test.com"}):
        second = _login_account_key()
    with app.test_request_context("/api/auth/login", method="POST", json={"email": "other@test.com"}):
        other = _login_account_key()
    assert first == second
    assert first != other
    assert first.startswith("login-account:")


def test_login_throttle_falls_back_to_the_client_address_without_an_email(app):
    with app.test_request_context("/api/auth/login", method="POST", json={}):
        assert _login_account_key().startswith("login-ip:")


# ---------- Categories ----------

def test_categories_list_counts_items_and_are_admin_only(app, owner_client, kitchen_client, anon_client):
    db.session.add(MenuCategory(name="Snacks"))
    db.session.add(MenuItem(name="Samosa", category="Snacks", price_paise=1500, is_available=True))
    db.session.commit()
    rows = owner_client.get("/api/admin/categories").get_json()["categories"]
    assert rows == [{
        "id": rows[0]["id"], "name": "Snacks", "item_count": 1,
        "created_at": rows[0]["created_at"], "updated_at": rows[0]["updated_at"],
    }]
    assert kitchen_client.get("/api/admin/categories").status_code == 403
    assert anon_client.get("/api/admin/categories").status_code == 401


def test_category_names_are_unique_ignoring_case(owner_client):
    assert owner_client.post("/api/admin/categories", json={"name": "Beverages"}).status_code == 201
    duplicate = owner_client.post("/api/admin/categories", json={"name": "  beverages "})
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "CATEGORY_EXISTS"


def test_blank_category_name_is_a_validation_error_with_details(owner_client):
    response = owner_client.post("/api/admin/categories", json={"name": "   "})
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["details"]["name"] == "Cannot be empty."


def test_renaming_a_category_moves_its_items(owner_client):
    db.session.add(MenuCategory(name="Drinks"))
    db.session.add(MenuItem(name="Tea", category="Drinks", price_paise=1000, is_available=True))
    db.session.commit()
    category_id = MenuCategory.query.filter_by(name="Drinks").one().id

    response = owner_client.patch(f"/api/admin/categories/{category_id}", json={"name": "Hot Drinks"})
    assert response.status_code == 200
    assert response.get_json()["category"]["name"] == "Hot Drinks"
    assert MenuItem.query.filter_by(name="Tea").one().category == "Hot Drinks"


def test_category_in_use_cannot_be_deleted_but_an_unused_one_can(owner_client):
    db.session.add(MenuCategory(name="Meals"))
    db.session.add(MenuCategory(name="Empty"))
    db.session.add(MenuItem(name="Thali", category="Meals", price_paise=8000, is_available=True))
    db.session.commit()
    meals = MenuCategory.query.filter_by(name="Meals").one().id
    empty = MenuCategory.query.filter_by(name="Empty").one().id

    blocked = owner_client.delete(f"/api/admin/categories/{meals}")
    assert blocked.status_code == 409
    assert blocked.get_json()["error"]["code"] == "CATEGORY_IN_USE"

    assert owner_client.delete(f"/api/admin/categories/{empty}").status_code == 200
    assert db.session.get(MenuCategory, empty) is None


def test_unknown_category_returns_not_found(owner_client):
    assert owner_client.patch("/api/admin/categories/99999", json={"name": "x"}).status_code == 404
    assert owner_client.delete("/api/admin/categories/99999").status_code == 404


def test_menu_items_must_use_an_existing_category(owner_client):
    response = owner_client.post("/api/admin/menu", json={
        "name": "Mystery Roll", "category": "Nowhere", "price_paise": 4500,
    })
    assert response.status_code == 400
    assert "category" in response.get_json()["details"]


def test_menu_item_category_is_matched_case_insensitively_and_stored_in_canonical_form(owner_client):
    db.session.add(MenuCategory(name="Snacks"))
    db.session.commit()
    response = owner_client.post("/api/admin/menu", json={
        "name": "Puff", "category": "snacks", "price_paise": 2500,
    })
    assert response.status_code == 201
    assert response.get_json()["item"]["category"] == "Snacks"


# ---------- Canteen details ----------

def test_canteen_settings_have_defaults_before_anything_is_saved(owner_client):
    data = owner_client.get("/api/admin/canteen/settings").get_json()
    assert data["canteen_name"] == "TrayUP Canteen"
    assert data["opens_at"] is None and data["closes_at"] is None
    assert data["is_accepting_orders"] is True


def test_canteen_details_are_saved_and_shown_to_students(owner_client, anon_client):
    response = owner_client.patch("/api/admin/canteen/settings", json={
        "canteen_name": "  Main   Block  Canteen ", "opens_at": "08:30", "closes_at": "18:00",
    })
    assert response.status_code == 200
    assert response.get_json()["canteen_name"] == "Main Block Canteen"

    stored = CanteenSettings.query.get(1)
    assert (stored.canteen_name, stored.opens_at, stored.closes_at) == ("Main Block Canteen", "08:30", "18:00")

    public = anon_client.get("/api/canteen/status").get_json()
    assert public["canteen_name"] == "Main Block Canteen"
    assert public["opens_at"] == "08:30"
    assert public["is_accepting_orders"] is True


def test_hours_can_be_cleared_together(owner_client):
    owner_client.patch("/api/admin/canteen/settings", json={"opens_at": "08:00", "closes_at": "18:00"})
    response = owner_client.patch("/api/admin/canteen/settings", json={"opens_at": None, "closes_at": None})
    assert response.status_code == 200
    assert response.get_json()["opens_at"] is None


@pytest.mark.parametrize("payload, field", [
    ({"opens_at": "08:00"}, "hours"),
    ({"opens_at": "18:00", "closes_at": "08:00"}, "hours"),
    ({"opens_at": "25:00", "closes_at": "26:00"}, "opens_at"),
    ({"canteen_name": "   "}, "canteen_name"),
    ({"canteen_name": "x" * 81}, "canteen_name"),
    ({"unknown": 1}, "unknown_fields"),
    ({}, "body"),
])
def test_invalid_canteen_details_are_refused_with_field_errors(owner_client, payload, field):
    response = owner_client.patch("/api/admin/canteen/settings", json=payload)
    assert response.status_code == 400
    assert field in response.get_json()["details"]


def test_canteen_details_are_admin_only(kitchen_client, client):
    assert kitchen_client.patch("/api/admin/canteen/settings", json={"canteen_name": "X"}).status_code == 403
    assert client.get("/api/admin/canteen/settings").status_code == 403
