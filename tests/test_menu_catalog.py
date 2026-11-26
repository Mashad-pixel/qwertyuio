import pytest

from app.extensions import db
from app.models.menu import MenuItem
from app.models.order import OrderStatus
from app.models.user import User, UserRole
from app.services.order_service import create_order
from tests.session_helpers import issue_test_session


def _user(email, role):
    user = User(name=email.split("@")[0], email=email, role=role, is_active=True)
    user.set_password("StrongPass123!")
    db.session.add(user)
    db.session.commit()
    return user


def _signed_in(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["sid"] = issue_test_session(user)
    return client


# ---------- Public menu ----------

def test_public_menu_carries_diet_and_details_and_hides_unavailable_items(app, menu):
    samosa = menu["samosa"]
    samosa.is_veg = True
    samosa.ingredients = ["Flour", "Potato"]
    samosa.recipe_steps = ["Fold the dough", "Fry until golden"]
    samosa.preparation = "Fried fresh."
    db.session.commit()

    items = {entry["name"]: entry for entry in app.test_client().get("/api/menu").get_json()["items"]}
    assert "Burger" not in items  # is_available is False
    assert items["Samosa"]["is_veg"] is True
    assert items["Samosa"]["ingredients"] == ["Flour", "Potato"]
    assert items["Samosa"]["recipe_steps"] == ["Fold the dough", "Fry until golden"]
    assert items["Samosa"]["preparation"] == "Fried fresh."
    assert items["Samosa"]["is_available"] is True
    # Diet not recorded stays null, rather than being guessed.
    assert items["Tea"]["is_veg"] is None


def test_menu_detail_returns_unavailable_items_with_their_status(app, menu):
    response = app.test_client().get(f"/api/menu/{menu['burger'].id}")
    assert response.status_code == 200
    assert response.get_json()["item"]["is_available"] is False


def test_menu_detail_returns_404_for_unknown_items(app):
    response = app.test_client().get("/api/menu/9999")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "MENU_ITEM_NOT_FOUND"


# ---------- Popularity ----------

def test_popularity_counts_only_orders_that_were_placed(app, menu):
    student = _user("popular-student@test.com", UserRole.STUDENT)

    pending, _ = create_order(student.id, [{"menu_item_id": menu["samosa"].id, "quantity": 2}])
    assert pending.order_status == OrderStatus.PENDING_PAYMENT

    cancelled, _ = create_order(student.id, [{"menu_item_id": menu["tea"].id, "quantity": 5}])
    cancelled.order_status = OrderStatus.CANCELLED

    placed, _ = create_order(student.id, [{"menu_item_id": menu["samosa"].id, "quantity": 1}])
    placed.order_status = OrderStatus.RECEIVED
    db.session.commit()

    response = app.test_client().get("/api/menu/popular?period=month")
    assert response.status_code == 200
    assert response.get_json()["items"] == [{"menu_item_id": menu["samosa"].id, "quantity": 1}]


def test_popularity_rejects_unknown_periods(app):
    response = app.test_client().get("/api/menu/popular?period=decade")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_PERIOD"


# ---------- Admin validation of the new fields ----------

def _admin_client(app):
    return _signed_in(app, _user("catalog-admin@test.com", UserRole.ADMIN))


def _payload(**extra):
    payload = {"name": "Test Dish", "category": "Snacks", "price_paise": 4000}
    payload.update(extra)
    return payload


def test_admin_can_record_diet_and_preparation_details(app):
    client = _admin_client(app)
    response = client.post("/api/admin/menu", json=_payload(
        is_veg=True,
        ingredients=["Chickpea flour", " Onion "],
        recipe_steps=["Mix the batter"],
        preparation="Made to order.",
    ))
    assert response.status_code == 201
    item = response.get_json()["item"]
    assert item["is_veg"] is True
    assert item["ingredients"] == ["Chickpea flour", "Onion"]
    assert item["recipe_steps"] == ["Mix the batter"]
    assert item["preparation"] == "Made to order."


@pytest.mark.parametrize(
    "extra",
    [
        {"is_veg": "yes"},
        {"ingredients": "rice"},
        {"ingredients": ["ok", "   "]},
        {"ingredients": ["x" * 121]},
        {"ingredients": ["x"] * 41},
        {"recipe_steps": [123]},
        {"recipe_steps": ["x" * 401]},
        {"preparation": "x" * 1001},
    ],
)
def test_admin_rejects_malformed_detail_fields(app, extra):
    response = _admin_client(app).post("/api/admin/menu", json=_payload(**extra))
    assert response.status_code == 400
    assert response.get_json()["details"]


# ---------- Seeding ----------

def test_seed_menu_loads_the_starter_catalogue_once(app):
    runner = app.test_cli_runner()

    first = runner.invoke(args=["seed-menu"])
    assert first.exit_code == 0, first.output
    assert "Loaded 43 menu items." in first.output
    assert MenuItem.query.count() == 43

    second = runner.invoke(args=["seed-menu"])
    assert second.exit_code == 0
    assert "Nothing was loaded" in second.output
    assert MenuItem.query.count() == 43
