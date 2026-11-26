"""Admin-only management: menu categories, canteen details, staff accounts, and related fixes."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.config import validate_rate_limit_storage
from app.extensions import db
from app.models.canteen import CanteenSettings
from app.models.menu import MenuItem
from app.models.menu_category import MenuCategory
from app.models.order import Order, OrderStatus
from app.models.payment import Payment
from app.models.stock_reservation import ReservationStatus, StockReservation
from app.models.user import User, UserRole
from app.services.order_service import cancel_order
from app.services.payment_service import _confirm_captured_payment, create_payment_order
from presence_helpers import create_order_for, presence_headers_for


def make_user(email, role, name="Test User", password="StrongPass123!"):
    user = User(name=name, email=email, role=role, is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def logged_in(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return client


@pytest.fixture
def admin(app):
    return make_user("admin@test.com", UserRole.ADMIN, name="Admin")


@pytest.fixture
def admin_client(app, admin):
    return logged_in(app, admin)


@pytest.fixture
def kitchen(app):
    return make_user("kitchen@test.com", UserRole.KITCHEN, name="Kitchen")


@pytest.fixture
def kitchen_client(app, kitchen):
    return logged_in(app, kitchen)


@pytest.fixture
def categories(app, menu):
    rows = {}
    for index, name in enumerate(["Snacks", "Drinks", "Meals"]):
        row = MenuCategory(name=name, sort_order=index * 10)
        db.session.add(row)
        rows[name] = row
    db.session.commit()
    return rows


# ---------- Menu categories ----------

def test_categories_list_counts_items_and_is_admin_only(admin_client, kitchen_client, anon_client, client, categories, menu):
    listed = admin_client.get("/api/admin/categories").get_json()["categories"]
    counts = {row["name"]: row["item_count"] for row in listed}
    assert counts["Snacks"] == 1
    assert counts["Meals"] == 2

    assert kitchen_client.get("/api/admin/categories").status_code == 403
    assert client.get("/api/admin/categories").status_code == 403
    assert anon_client.get("/api/admin/categories").status_code in (302, 401)


def test_create_category_trims_and_rejects_case_insensitive_duplicates(admin_client, categories):
    created = admin_client.post("/api/admin/categories", json={"name": "  Hot    Drinks "})
    assert created.status_code == 201
    assert created.get_json()["category"]["name"] == "Hot Drinks"

    duplicate = admin_client.post("/api/admin/categories", json={"name": "hot drinks"})
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "CATEGORY_NAME_TAKEN"


@pytest.mark.parametrize("payload", [{}, {"name": "   "}, {"name": "x" * 61}, {"name": 5}, {"name": "A", "colour": "red"}])
def test_invalid_category_payloads_are_rejected(admin_client, payload):
    response = admin_client.post("/api/admin/categories", json=payload)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_FAILED"


def test_renaming_a_category_moves_its_items_in_the_same_change(admin_client, categories, menu):
    response = admin_client.patch(f"/api/admin/categories/{categories['Snacks'].id}", json={"name": "Quick Bites"})
    assert response.status_code == 200
    assert response.get_json()["category"]["name"] == "Quick Bites"
    assert db.session.get(MenuItem, menu["samosa"].id).category == "Quick Bites"


def test_rename_to_an_existing_name_is_rejected(admin_client, categories):
    response = admin_client.patch(f"/api/admin/categories/{categories['Snacks'].id}", json={"name": "drinks"})
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "CATEGORY_NAME_TAKEN"


def test_sort_order_can_be_changed(admin_client, categories):
    response = admin_client.patch(f"/api/admin/categories/{categories['Meals'].id}", json={"sort_order": 5})
    assert response.get_json()["category"]["sort_order"] == 5


def test_category_in_use_cannot_be_deleted_but_unused_one_can(admin_client, categories, menu):
    in_use = admin_client.delete(f"/api/admin/categories/{categories['Snacks'].id}")
    assert in_use.status_code == 409
    assert in_use.get_json()["error"]["code"] == "CATEGORY_IN_USE"

    unused = MenuCategory(name="Desserts", sort_order=90)
    db.session.add(unused)
    db.session.commit()
    assert admin_client.delete(f"/api/admin/categories/{unused.id}").status_code == 200
    assert db.session.get(MenuCategory, unused.id) is None


def test_menu_items_must_use_an_existing_category(admin_client, categories):
    response = admin_client.post("/api/admin/menu", json={
        "name": "Mystery Dish", "category": "Not A Category", "price_paise": 1000,
    })
    assert response.status_code == 400
    assert "category" in response.get_json()["details"]


def test_public_menu_follows_the_category_order(app, client, categories, menu):
    # Drinks (sort 10) should come before Snacks (sort 0) once the order is changed.
    categories["Snacks"].sort_order = 50
    categories["Drinks"].sort_order = 5
    db.session.commit()
    items = client.get("/api/menu").get_json()["items"]
    categories_in_order = [item["category"] for item in items]
    assert categories_in_order.index("Drinks") < categories_in_order.index("Snacks")


# ---------- Canteen details ----------

def test_canteen_settings_have_defaults_and_persist_changes(admin_client):
    defaults = admin_client.get("/api/admin/canteen/settings").get_json()
    assert defaults["canteen_name"] == "TrayUP Canteen"
    assert (defaults["opens_at"], defaults["closes_at"]) == ("08:00", "18:00")
    assert defaults["is_accepting_orders"] is True

    saved = admin_client.patch("/api/admin/canteen/settings", json={
        "canteen_name": "  North  Block Canteen ", "opens_at": "07:30", "closes_at": "17:00",
    })
    assert saved.status_code == 200
    body = saved.get_json()
    assert body["canteen_name"] == "North Block Canteen"
    assert (body["opens_at"], body["closes_at"]) == ("07:30", "17:00")

    stored = db.session.get(CanteenSettings, 1)
    assert stored.canteen_name == "North Block Canteen"


def test_open_close_switch_does_not_overwrite_name_or_hours(admin_client):
    admin_client.patch("/api/admin/canteen/settings", json={"canteen_name": "Main Canteen"})
    admin_client.patch("/api/admin/canteen/status", json={"is_accepting_orders": False, "closed_message": "Exams"})
    settings = admin_client.get("/api/admin/canteen/settings").get_json()
    assert settings["canteen_name"] == "Main Canteen"
    assert settings["is_accepting_orders"] is False


@pytest.mark.parametrize("payload, field", [
    ({"opens_at": "9am"}, "opens_at"),
    ({"opens_at": "25:00"}, "opens_at"),
    ({"closes_at": "7:00"}, "closes_at"),
    ({"canteen_name": ""}, "canteen_name"),
    ({"canteen_name": "x" * 121}, "canteen_name"),
    ({"opens_at": "18:00", "closes_at": "08:00"}, "closes_at"),
    ({"opens_at": "09:00", "closes_at": "09:00"}, "closes_at"),
    ({"timezone": "Asia/Kolkata"}, "unknown_fields"),
])
def test_invalid_canteen_details_are_rejected(admin_client, payload, field):
    response = admin_client.patch("/api/admin/canteen/settings", json=payload)
    assert response.status_code == 400
    assert field in response.get_json()["details"]


def test_canteen_details_are_admin_only(kitchen_client, client):
    assert kitchen_client.patch("/api/admin/canteen/settings", json={"canteen_name": "X"}).status_code == 403
    assert client.get("/api/admin/canteen/settings").status_code == 403


def test_public_status_shape_is_unchanged(anon_client):
    assert set(anon_client.get("/api/canteen/status").get_json()) == {"is_accepting_orders", "message"}


# ---------- Staff accounts ----------

def test_staff_list_contains_only_admins_and_kitchen_staff(admin_client, kitchen, student):
    staff = admin_client.get("/api/admin/staff").get_json()["staff"]
    emails = {row["email"] for row in staff}
    assert {"admin@test.com", "kitchen@test.com"} <= emails
    assert student.email not in emails
    assert all("password_hash" not in row for row in staff)


def test_staff_management_is_admin_only(kitchen_client, client, anon_client, kitchen):
    assert kitchen_client.get("/api/admin/staff").status_code == 403
    assert kitchen_client.post("/api/admin/staff", json={}).status_code == 403
    assert client.get("/api/admin/staff").status_code == 403
    assert anon_client.get("/api/admin/staff").status_code in (302, 401)


def test_admin_creates_a_kitchen_account_that_can_then_sign_in(admin_client, anon_client):
    created = admin_client.post("/api/admin/staff", json={
        "name": "  Ravi  Kumar ", "email": " Ravi@Canteen.EDU ", "password": "KitchenPass1", "role": "kitchen",
    })
    assert created.status_code == 201
    staff = created.get_json()["staff"]
    assert staff["email"] == "ravi@canteen.edu"
    assert staff["role"] == UserRole.KITCHEN
    assert staff["name"] == "Ravi Kumar"

    login = anon_client.post("/api/auth/login", json={"email": "ravi@canteen.edu", "password": "KitchenPass1"})
    assert login.status_code == 200
    assert login.get_json()["data"]["role"] == UserRole.KITCHEN


def test_staff_cannot_be_created_as_student_or_with_weak_password(admin_client):
    as_student = admin_client.post("/api/admin/staff", json={
        "name": "A", "email": "a@x.com", "password": "LongEnough1", "role": "STUDENT",
    })
    assert as_student.status_code == 400
    assert "role" in as_student.get_json()["details"]

    weak = admin_client.post("/api/admin/staff", json={
        "name": "A", "email": "b@x.com", "password": "onlyletters", "role": "ADMIN",
    })
    assert weak.status_code == 400
    assert "password" in weak.get_json()["details"]


def test_duplicate_staff_email_is_rejected(admin_client, kitchen):
    response = admin_client.post("/api/admin/staff", json={
        "name": "Dup", "email": "KITCHEN@test.com", "password": "LongEnough1", "role": "KITCHEN",
    })
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "EMAIL_UNAVAILABLE"


def test_role_change_takes_effect_immediately(app, admin_client, kitchen):
    response = admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"role": "ADMIN"})
    assert response.status_code == 200
    assert response.get_json()["staff"]["role"] == UserRole.ADMIN
    # The same session can now use admin routes, because role is read from the database each request.
    assert logged_in(app, kitchen).get("/api/admin/staff").status_code == 200


def test_deactivated_staff_session_stops_working(app, admin_client, kitchen):
    kitchen_session = logged_in(app, kitchen)
    assert kitchen_session.get("/api/auth/me").status_code == 200

    response = admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"is_active": False})
    assert response.status_code == 200
    assert response.get_json()["staff"]["is_active"] is False
    assert kitchen_session.get("/api/auth/me").status_code == 401


def test_administrator_cannot_change_their_own_access(admin_client, admin):
    demote = admin_client.patch(f"/api/admin/staff/{admin.id}", json={"role": "KITCHEN"})
    assert demote.status_code == 409
    assert demote.get_json()["error"]["code"] == "SELF_CHANGE_NOT_ALLOWED"

    deactivate = admin_client.patch(f"/api/admin/staff/{admin.id}", json={"is_active": False})
    assert deactivate.status_code == 409

    rename = admin_client.patch(f"/api/admin/staff/{admin.id}", json={"name": "Chief Admin"})
    assert rename.status_code == 200


def test_last_active_administrator_cannot_be_removed(app, kitchen):
    from app.services.errors import OrderError
    from app.services.staff_service import update_staff

    lone_admin = make_user("lone@test.com", UserRole.ADMIN, name="Lone")
    # Only an active administrator can act, so the actor here is a kitchen account that calls the
    # service directly. The rule must still hold.
    with pytest.raises(OrderError) as excinfo:
        update_staff(lone_admin, {"is_active": False}, actor=kitchen)
    assert excinfo.value.code == "LAST_ADMIN"
    assert db.session.get(User, lone_admin.id).is_active is True


def test_staff_routes_do_not_touch_students(admin_client, student):
    response = admin_client.patch(f"/api/admin/staff/{student.id}", json={"is_active": False})
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "STAFF_NOT_FOUND"
    assert db.session.get(User, student.id).is_active is True


def test_staff_update_rejects_bad_values(admin_client, kitchen):
    assert admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"role": "STUDENT"}).status_code == 400
    assert admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"is_active": "no"}).status_code == 400
    assert admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={"password_hash": "x"}).status_code == 400
    assert admin_client.patch(f"/api/admin/staff/{kitchen.id}", json={}).status_code == 400


# ---------- Reporting dates (exclusive end boundary) ----------

def _order_at(student, menu, created_utc):
    order, _ = create_order_for(student.id, [{"menu_item_id": menu["tea"].id, "quantity": 1}])
    stored = db.session.get(Order, order.id)
    stored.created_at = created_utc
    db.session.commit()
    return stored


def test_orders_late_on_the_last_selected_day_are_included(admin_client, student, menu):
    # 10:00 on 2026-02-10 in India (UTC+05:30) is 04:30 UTC the same day.
    # Passing the date straight through used to drop it, because it compared against midnight UTC.
    _order_at(student, menu, datetime(2026, 2, 10, 4, 30, tzinfo=timezone.utc))

    overview = admin_client.get("/api/admin/reports/overview?from=2026-02-10&to=2026-02-10").get_json()["data"]
    assert overview["total_orders"] == 1



def test_orders_on_the_day_before_are_not_counted_for_a_one_day_range(admin_client, student, menu):
    # 23:30 on 2026-02-09 in India is 18:00 UTC on 2026-02-09, outside a 2026-02-10 range.
    _order_at(student, menu, datetime(2026, 2, 9, 18, 0, tzinfo=timezone.utc))
    overview = admin_client.get("/api/admin/reports/overview?from=2026-02-10&to=2026-02-10").get_json()["data"]
    assert overview["total_orders"] == 0


# ---------- Reservations after a paid cancellation ----------

def _pay(student, menu, key, quantity):
    order, _ = create_order_for(student.id, [{"menu_item_id": menu[key].id, "quantity": quantity}])
    fake = MagicMock()
    fake.order.create.return_value = {"id": f"order_{uuid.uuid4().hex[:12]}"}
    with patch("app.services.payment_service.get_razorpay_client", return_value=fake):
        payment, _ = create_payment_order(order.id, student.id)
    _confirm_captured_payment(
        payment,
        provider_payment_id=f"pay_{uuid.uuid4().hex[:12]}",
        amount_paise=order.total_paise,
        currency="INR",
    )
    return db.session.get(Order, order.id)


def test_cancelling_a_paid_order_marks_its_reservation_released(student, menu):
    paid = _pay(student, menu, "paneer_roll", 1)
    reservation = StockReservation.query.filter_by(order_id=paid.id).one()
    assert reservation.status == ReservationStatus.COMMITTED

    cancel_order(paid.id, staff_user_id=1, reason="Kitchen closed")

    assert StockReservation.query.filter_by(order_id=paid.id).one().status == ReservationStatus.RELEASED
    assert db.session.get(MenuItem, menu["paneer_roll"].id).stock_quantity == 2


# ---------- Rate-limit storage in production ----------

def test_production_requires_a_shared_rate_limit_store():
    with pytest.raises(RuntimeError, match="shared rate-limit store"):
        validate_rate_limit_storage({"RATELIMIT_STORAGE_URI": "memory://", "RATELIMIT_ALLOW_MEMORY": False}, "production")
    validate_rate_limit_storage({"RATELIMIT_STORAGE_URI": "redis://cache:6379/0"}, "production")
    validate_rate_limit_storage({"RATELIMIT_STORAGE_URI": "rediss://cache:6380/0"}, "production")
    validate_rate_limit_storage({"RATELIMIT_STORAGE_URI": "memory://", "RATELIMIT_ALLOW_MEMORY": True}, "production")
    validate_rate_limit_storage({"RATELIMIT_STORAGE_URI": "memory://"}, "development")
