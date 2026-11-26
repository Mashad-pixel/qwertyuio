"""GET /api/menu/popular: the only popularity data the student app is allowed to show.

It must count only paid orders, use canteen-local days, and expose no student or revenue data.
"""
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.menu import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem
from tests.test_reports import pay


def place(student, menu, key, quantity, days_ago=0):
    order = pay(student, key, menu, quantity)
    stored = db.session.get(Order, order.id)
    stored.created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    db.session.commit()
    return stored


def counts(client, period=None):
    query = f"?period={period}" if period else ""
    response = client.get(f"/api/menu/popular{query}")
    assert response.status_code == 200, response.get_data(as_text=True)
    return {row["menu_item_id"]: row["quantity"] for row in response.get_json()["items"]}


def test_is_public_and_needs_no_login(anon_client):
    response = anon_client.get("/api/menu/popular")

    assert response.status_code == 200
    assert response.get_json()["period"] == "day"


def test_counts_todays_paid_units_per_item(client, student, menu):
    place(student, menu, "samosa", 2)
    place(student, menu, "samosa", 1)
    place(student, menu, "tea", 4)

    result = counts(client, "day")

    assert result == {menu["samosa"].id: 3, menu["tea"].id: 4}


def test_unpaid_orders_are_not_popular(client, student, menu):
    from app.services.order_service import create_order

    create_order(student.id, [{"menu_item_id": menu["tea"].id, "quantity": 5}])

    assert counts(client, "day") == {}


def test_orders_from_older_days_only_count_in_wider_periods(client, student, menu):
    place(student, menu, "tea", 1, days_ago=3)

    assert counts(client, "day") == {}
    assert counts(client, "week") == {menu["tea"].id: 1}
    assert counts(client, "month") == {menu["tea"].id: 1}


def test_orders_older_than_a_month_are_excluded(client, student, menu):
    place(student, menu, "tea", 1, days_ago=45)

    assert counts(client, "month") == {}


def test_default_period_is_day(client, student, menu):
    place(student, menu, "tea", 2, days_ago=3)

    assert client.get("/api/menu/popular").get_json()["period"] == "day"
    assert counts(client) == {}


def test_response_exposes_only_item_ids_and_counts(client, student, menu):
    place(student, menu, "tea", 1)

    body = client.get("/api/menu/popular?period=day").get_json()

    assert set(body) == {"period", "items"}
    assert set(body["items"][0]) == {"menu_item_id", "quantity"}
    assert student.email not in str(body)


def test_items_removed_from_the_menu_are_left_out(client, student, menu):
    place(student, menu, "samosa", 2)
    place(student, menu, "tea", 1)
    samosa_id = menu["samosa"].id
    db.session.delete(db.session.get(MenuItem, samosa_id))
    # SQLite does not enforce foreign keys here. Apply the schema's ON DELETE SET NULL rule
    # by hand, as Postgres does for order_items.menu_item_id.
    OrderItem.query.filter_by(menu_item_id=samosa_id).update({"menu_item_id": None})
    db.session.commit()

    assert counts(client, "day") == {menu["tea"].id: 1}


def test_unknown_period_is_rejected(anon_client):
    response = anon_client.get("/api/menu/popular?period=year")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_PERIOD"
