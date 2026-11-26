"""Admin menu deletion and category management."""
import pytest

from app.extensions import db
from app.models.menu import MenuItem
from app.models.menu_category import MenuCategory
from app.models.order_item import OrderItem
from app.models.stock_reservation import ReservationStatus, StockReservation
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
    return client


@pytest.fixture
def admin_client(app):
    return _client_for_role(app, UserRole.ADMIN, "admin-menu@test.com")


@pytest.fixture
def kitchen_client(app):
    return _client_for_role(app, UserRole.KITCHEN, "kitchen-menu@test.com")


@pytest.fixture
def categories(app, menu):
    # The `menu` fixture uses these category names, so each one must exist as a category.
    rows = {}
    for name in ("Snacks", "Drinks", "Meals"):
        rows[name] = MenuCategory(name=name)
        db.session.add(rows[name])
    db.session.commit()
    return rows


def _order_for(client, menu_key, menu, quantity=1):
    return client.post(
        "/api/orders",
        json={"items": [{"menu_item_id": menu[menu_key].id, "quantity": quantity}]},
        headers={"Idempotency-Key": f"key-{menu_key}-{quantity}"},
    )


# --- Deleting menu items -----------------------------------------------------------------------

def test_admin_deletes_an_item_and_its_past_order_lines_keep_their_sales(admin_client, menu, client):
    samosa_id = menu["samosa"].id
    created = _order_for(client, "samosa", menu)
    assert created.status_code == 201
    order_line = OrderItem.query.filter_by(menu_item_id=samosa_id).one()

    response = admin_client.delete(f"/api/admin/menu/{samosa_id}")

    assert response.status_code == 200
    assert response.get_json()["deleted"] == samosa_id
    assert db.session.get(MenuItem, samosa_id) is None
    db.session.refresh(order_line)
    assert order_line.menu_item_id is None
    assert order_line.item_name_snapshot == "Samosa"


def test_delete_is_refused_while_an_order_is_holding_stock(admin_client, menu, client):
    paneer = menu["paneer_roll"]
    assert _order_for(client, "paneer_roll", menu).status_code == 201

    response = admin_client.delete(f"/api/admin/menu/{paneer.id}")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "MENU_ITEM_IN_USE"
    assert db.session.get(MenuItem, paneer.id) is not None


def test_delete_is_refused_when_reserved_quantity_is_set_without_a_reservation_row(admin_client, menu):
    paneer = menu["paneer_roll"]
    paneer.reserved_quantity = 1
    db.session.commit()

    response = admin_client.delete(f"/api/admin/menu/{paneer.id}")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "MENU_ITEM_IN_USE"


def test_delete_removes_sold_and_released_stock_rows(admin_client, menu, client):
    paneer = menu["paneer_roll"]
    assert _order_for(client, "paneer_roll", menu).status_code == 201
    # Simulate payment confirmation: the held unit is now sold, so nothing is held any more.
    reservation = StockReservation.query.filter_by(menu_item_id=paneer.id).one()
    reservation.status = ReservationStatus.COMMITTED
    paneer.reserved_quantity = 0
    db.session.commit()

    response = admin_client.delete(f"/api/admin/menu/{paneer.id}")

    assert response.status_code == 200
    assert StockReservation.query.filter_by(menu_item_id=paneer.id).count() == 0


def test_deleting_a_missing_item_returns_404(admin_client):
    response = admin_client.delete("/api/admin/menu/99999")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "MENU_ITEM_NOT_FOUND"


# --- Categories --------------------------------------------------------------------------------

def test_list_categories_includes_item_counts(admin_client, categories, menu):
    response = admin_client.get("/api/admin/categories")

    assert response.status_code == 200
    by_name = {row["name"]: row for row in response.get_json()["categories"]}
    assert by_name["Snacks"]["item_count"] == 1
    assert by_name["Drinks"]["item_count"] == 1
    assert by_name["Meals"]["item_count"] == 2


def test_admin_creates_a_category(admin_client):
    response = admin_client.post("/api/admin/categories", json={"name": "  Breakfast  "})

    assert response.status_code == 201
    category = response.get_json()["category"]
    assert category["name"] == "Breakfast"
    assert category["item_count"] == 0


@pytest.mark.parametrize("name", ["snacks", "SNACKS", " Snacks "])
def test_category_names_are_unique_ignoring_case(admin_client, categories, name):
    response = admin_client.post("/api/admin/categories", json={"name": name})

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "CATEGORY_EXISTS"


@pytest.mark.parametrize("payload", [{}, {"name": ""}, {"name": "   "}, {"name": 5}, {"name": "x" * 61}])
def test_category_name_is_validated(admin_client, payload):
    response = admin_client.post("/api/admin/categories", json=payload)

    assert response.status_code == 400
    assert "name" in response.get_json()["details"]


def test_category_request_body_must_be_an_object(admin_client):
    response = admin_client.post("/api/admin/categories", json=["Snacks"])

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_JSON"


def test_renaming_a_category_moves_its_menu_items(admin_client, categories, menu):
    snacks_id = categories["Snacks"].id

    response = admin_client.patch(f"/api/admin/categories/{snacks_id}", json={"name": "Quick bites"})

    assert response.status_code == 200
    body = response.get_json()["category"]
    assert body["name"] == "Quick bites"
    assert body["item_count"] == 1
    db.session.refresh(menu["samosa"])
    assert menu["samosa"].category == "Quick bites"


def test_renaming_to_an_existing_name_is_refused(admin_client, categories):
    response = admin_client.patch(
        f"/api/admin/categories/{categories['Snacks'].id}",
        json={"name": "drinks"},
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "CATEGORY_EXISTS"


def test_renaming_to_the_same_name_is_allowed(admin_client, categories):
    response = admin_client.patch(
        f"/api/admin/categories/{categories['Snacks'].id}",
        json={"name": "Snacks"},
    )
    assert response.status_code == 200


def test_category_in_use_cannot_be_deleted(admin_client, categories, menu):
    response = admin_client.delete(f"/api/admin/categories/{categories['Snacks'].id}")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "CATEGORY_IN_USE"
    assert db.session.get(MenuCategory, categories["Snacks"].id) is not None


def test_unused_category_can_be_deleted(admin_client):
    created = admin_client.post("/api/admin/categories", json={"name": "Seasonal"}).get_json()["category"]

    response = admin_client.delete(f"/api/admin/categories/{created['id']}")

    assert response.status_code == 200
    assert db.session.get(MenuCategory, created["id"]) is None


def test_missing_category_returns_404(admin_client):
    assert admin_client.patch("/api/admin/categories/99999", json={"name": "X"}).status_code == 404
    assert admin_client.delete("/api/admin/categories/99999").status_code == 404


def test_menu_item_must_use_an_existing_category(admin_client, categories):
    response = admin_client.post(
        "/api/admin/menu",
        json={"name": "Chai", "category": "Hot beverages", "price_paise": 1000},
    )

    assert response.status_code == 400
    assert "category" in response.get_json()["details"]


def test_menu_item_can_move_to_another_existing_category(admin_client, categories, menu):
    response = admin_client.patch(f"/api/admin/menu/{menu['samosa'].id}", json={"category": "Drinks"})

    assert response.status_code == 200
    assert response.get_json()["item"]["category"] == "Drinks"


def test_menu_item_move_to_unknown_category_is_refused(admin_client, categories, menu):
    response = admin_client.patch(f"/api/admin/menu/{menu['samosa'].id}", json={"category": "Nope"})

    assert response.status_code == 400
    assert "category" in response.get_json()["details"]


def test_kitchen_staff_cannot_manage_categories_or_delete_items(kitchen_client, menu):
    assert kitchen_client.get("/api/admin/categories").status_code == 403
    assert kitchen_client.post("/api/admin/categories", json={"name": "X"}).status_code == 403
    assert kitchen_client.delete(f"/api/admin/menu/{menu['samosa'].id}").status_code == 403
