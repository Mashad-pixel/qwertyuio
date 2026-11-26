from tests.session_helpers import issue_test_session
import pytest

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.user import User
from app.extensions import db


def post_order(client, items, key=None, **extra):
    headers = {}
    if key is not None:
        headers["Idempotency-Key"] = key
    body = {"items": items, **extra}
    return client.post("/api/orders", json=body, headers=headers)


def test_creates_order_with_server_side_total(client, menu):
    response = post_order(client, [
        {"menu_item_id": menu["samosa"].id, "quantity": 2},
        {"menu_item_id": menu["tea"].id, "quantity": 1},
    ])

    assert response.status_code == 201
    body = response.get_json()
    assert body["success"] is True

    data = body["data"]
    assert data["subtotal_paise"] == 4000  # 2 x 1500 + 1 x 1000
    assert data["total_paise"] == 4000
    assert data["order_status"] == "pending_payment"
    assert data["payment_status"] == "pending"
    assert "tracking_token" in data

    order = Order.query.one()
    assert order.total_paise == 4000
    assert OrderItem.query.count() == 2


def test_order_items_store_price_snapshots(client, menu):
    post_order(client, [{"menu_item_id": menu["samosa"].id, "quantity": 3}])

    item = OrderItem.query.one()
    assert item.item_name_snapshot == "Samosa"
    assert item.unit_price_snapshot_paise == 1500
    assert item.line_total_paise == 4500


def test_frontend_price_fields_are_ignored(client, menu):
    response = post_order(
        client,
        [{
            "menu_item_id": menu["samosa"].id,
            "quantity": 1,
            "unit_price_paise": 1,
        }],
        total_paise=1,
    )

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["total_paise"] == 1500
    assert data["items"][0]["unit_price_paise"] == 1500


def test_unavailable_item_is_rejected(client, menu):
    response = post_order(client, [{"menu_item_id": menu["burger"].id, "quantity": 1}])

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ITEM_UNAVAILABLE"
    assert Order.query.count() == 0


def test_missing_menu_item_returns_404(client, menu):
    response = post_order(client, [{"menu_item_id": 99999, "quantity": 1}])

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "MENU_ITEM_NOT_FOUND"


@pytest.mark.parametrize("bad_quantity", [0, -1, "2", True, 1.5, None])
def test_invalid_quantity_is_rejected(client, menu, bad_quantity):
    response = post_order(
        client,
        [{"menu_item_id": menu["samosa"].id, "quantity": bad_quantity}],
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_QUANTITY"
    assert Order.query.count() == 0


def test_quantity_above_limit_is_rejected(client, menu):
    response = post_order(
        client,
        [{"menu_item_id": menu["samosa"].id, "quantity": 21}],
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "QUANTITY_TOO_LARGE"
    assert Order.query.count() == 0


def test_insufficient_stock_is_rejected(client, menu):
    response = post_order(
        client,
        [{"menu_item_id": menu["paneer_roll"].id, "quantity": 3}],
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "INSUFFICIENT_STOCK"


def test_empty_order_is_rejected(client, menu):
    response = post_order(client, [])

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_ITEMS"
    assert Order.query.count() == 0


def test_repeated_menu_item_is_combined_into_one_line(client, menu):
    response = post_order(client, [
        {"menu_item_id": menu["samosa"].id, "quantity": 1},
        {"menu_item_id": menu["samosa"].id, "quantity": 2},
    ])

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert len(data["items"]) == 1
    assert data["items"][0]["quantity"] == 3
    assert data["total_paise"] == 4500


def test_invalid_idempotency_key_is_rejected(client, menu):
    response = post_order(
        client,
        [{"menu_item_id": menu["samosa"].id, "quantity": 1}],
        key="x" * 65,
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_IDEMPOTENCY_KEY"


def test_retry_with_same_key_returns_same_order(client, menu):
    items = [{"menu_item_id": menu["samosa"].id, "quantity": 1}]

    first = post_order(client, items, key="abc-123")
    second = post_order(client, items, key="abc-123")

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.get_json()["data"]["order_number"] == second.get_json()["data"]["order_number"]
    assert "tracking_token" not in second.get_json()["data"]
    assert Order.query.count() == 1


def test_requires_login(anon_client, menu):
    response = post_order(anon_client, [{"menu_item_id": menu["samosa"].id, "quantity": 1}])

    assert response.status_code in (302, 401)
    assert Order.query.count() == 0



def test_non_student_cannot_create_order(app, menu):
    staff = User(name="Kitchen Staff", email="kitchen-role-test@example.com", role="KITCHEN", is_active=True)
    staff.set_password("StrongPass123!")
    db.session.add(staff)
    db.session.commit()

    staff_client = app.test_client()
    with staff_client.session_transaction() as session:
        session["_user_id"] = str(staff.id)
        session["_fresh"] = True
        session["sid"] = issue_test_session(staff)

    response = post_order(staff_client, [{"menu_item_id": menu["samosa"].id, "quantity": 1}])

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"
    assert Order.query.count() == 0
