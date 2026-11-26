"""A reused Idempotency-Key may only return the order it was first used for, and only while it is live."""
from app.extensions import db
from app.models.order import Order, OrderStatus
from tests.test_order_details import post_order, tea


def _samosa(menu, quantity=1):
    return [{"menu_item_id": menu["samosa"].id, "quantity": quantity}]


def test_same_key_and_same_cart_returns_the_original_order(menu, student_client):
    first = post_order(student_client, tea(menu), key="same")
    again = post_order(student_client, tea(menu), key="same")

    assert first.status_code == 201
    assert again.status_code == 200
    assert again.get_json()["data"]["id"] == first.get_json()["data"]["id"]
    assert Order.query.count() == 1


def test_same_key_with_a_different_cart_is_refused(menu, student_client):
    post_order(student_client, tea(menu), key="cart-a")
    other = post_order(student_client, _samosa(menu), key="cart-a")

    assert other.status_code == 409
    assert other.get_json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert Order.query.count() == 1


def test_legacy_order_without_a_fingerprint_still_refuses_a_different_cart(menu, student_client):
    created = post_order(student_client, tea(menu), key="legacy")
    order = db.session.get(Order, created.get_json()["data"]["id"])
    order.request_fingerprint = None
    db.session.commit()

    other = post_order(student_client, _samosa(menu), key="legacy")

    assert other.status_code == 409
    assert other.get_json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_reused_key_for_a_cancelled_order_is_refused_and_creates_nothing(menu, student_client):
    created = post_order(student_client, tea(menu), key="gone")
    order = db.session.get(Order, created.get_json()["data"]["id"])
    order.order_status = OrderStatus.CANCELLED
    db.session.commit()

    retry = post_order(student_client, tea(menu), key="gone")

    assert retry.status_code == 409
    assert retry.get_json()["error"]["code"] == "ORDER_CANCELLED"
    assert Order.query.count() == 1


def test_a_new_key_after_a_cancelled_order_places_a_new_order(menu, student_client):
    created = post_order(student_client, tea(menu), key="gone-2")
    order = db.session.get(Order, created.get_json()["data"]["id"])
    order.order_status = OrderStatus.CANCELLED
    db.session.commit()

    fresh = post_order(student_client, tea(menu), key="fresh-key")

    assert fresh.status_code == 201
    assert Order.query.count() == 2
