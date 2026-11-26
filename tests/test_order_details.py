"""Checkout details on orders, and the idempotency fingerprint that stops a reused key from returning the wrong order."""
from app.extensions import db
from app.models.order import Order


def post_order(client, items, key="key-1", **details):
    body = {"items": items, **details}
    headers = {"Idempotency-Key": key} if key else {}
    return client.post("/api/orders", json=body, headers=headers)


def tea(menu, quantity=1):
    return [{"menu_item_id": menu["tea"].id, "quantity": quantity}]


def test_checkout_details_are_saved_and_returned(menu, student_client):
    response = post_order(
        student_client,
        tea(menu),
        customer_name="  Asha Rao ",
        customer_phone="98765 43210",
        instructions="Less sugar, please",
    )

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["customer_name"] == "Asha Rao"
    assert data["customer_phone"] == "+919876543210"
    assert data["instructions"] == "Less sugar, please"

    order = db.session.get(Order, data["id"])
    assert order.customer_name == "Asha Rao"
    assert order.customer_phone == "+919876543210"


def test_details_are_optional(menu, student_client):
    response = post_order(student_client, tea(menu))

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["customer_name"] is None
    assert data["customer_phone"] is None
    assert data["instructions"] is None


def test_invalid_phone_is_rejected_and_nothing_is_created(menu, student_client):
    response = post_order(student_client, tea(menu), customer_phone="12345")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_CUSTOMER_DETAILS"
    assert Order.query.count() == 0


def test_over_long_fields_are_rejected(menu, student_client):
    long_name = post_order(student_client, tea(menu), customer_name="x" * 101)
    long_note = post_order(student_client, tea(menu), instructions="y" * 501)

    assert long_name.status_code == 400
    assert long_note.status_code == 400
    assert Order.query.count() == 0


def test_non_text_details_are_rejected(menu, student_client):
    response = post_order(student_client, tea(menu), customer_name=["not", "text"])
    assert response.status_code == 400


def test_same_key_and_same_request_returns_the_original_order(menu, student_client):
    first = post_order(student_client, tea(menu), customer_name="Asha")
    second = post_order(student_client, tea(menu), customer_name="Asha")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.get_json()["data"]["id"] == first.get_json()["data"]["id"]
    assert Order.query.count() == 1


def test_same_key_with_different_items_is_refused(menu, student_client):
    original = post_order(student_client, tea(menu, quantity=1))
    changed = post_order(student_client, tea(menu, quantity=3))

    assert changed.status_code == 409
    assert changed.get_json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert Order.query.count() == 1
    assert Order.query.one().id == original.get_json()["data"]["id"]


def test_same_key_with_different_details_is_refused(menu, student_client):
    post_order(student_client, tea(menu), customer_name="Asha", instructions="No ice")
    changed = post_order(student_client, tea(menu), customer_name="Asha", instructions="Extra ice")

    assert changed.status_code == 409
    assert changed.get_json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_item_order_does_not_change_the_fingerprint(menu, student_client):
    both = [
        {"menu_item_id": menu["tea"].id, "quantity": 1},
        {"menu_item_id": menu["samosa"].id, "quantity": 2},
    ]
    first = post_order(student_client, both)
    reordered = post_order(student_client, list(reversed(both)))

    assert reordered.status_code == 200
    assert reordered.get_json()["data"]["id"] == first.get_json()["data"]["id"]


def test_orders_without_a_stored_fingerprint_are_compared_by_items(menu, student_client):
    # Orders created before fingerprints existed have none. They still must not match a different cart.
    created = post_order(student_client, tea(menu, quantity=1))
    order = db.session.get(Order, created.get_json()["data"]["id"])
    order.request_fingerprint = None
    db.session.commit()

    same_items = post_order(student_client, tea(menu, quantity=1))
    different = post_order(student_client, tea(menu, quantity=2))

    assert same_items.status_code == 200
    assert different.status_code == 409
