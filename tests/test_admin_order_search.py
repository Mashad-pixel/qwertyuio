import pytest

from app.extensions import db
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.user import User, UserRole


def make_user(email, name, role=UserRole.STUDENT):
    user = User(name=name, email=email, role=role, is_active=True)
    user.set_password("StudentPass123")
    db.session.add(user)
    db.session.commit()
    return user


def make_order(number, student, order_status=OrderStatus.RECEIVED, payment_status=PaymentStatus.PAID):
    order = Order(
        order_number=number,
        student_id=student.id,
        subtotal_paise=10000,
        total_paise=10000,
        order_status=order_status,
        payment_status=payment_status,
    )
    db.session.add(order)
    db.session.commit()
    return order


def client_for_admin(app):
    admin = make_user("admin-search@test.com", "Admin", role=UserRole.ADMIN)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True
    return client


@pytest.fixture
def seeded(app):
    aarav = make_user("aarav@test.com", "Aarav Shah")
    meera = make_user("meera@test.com", "Meera Iyer")
    make_order("TUP-1001", aarav, OrderStatus.PREPARING, PaymentStatus.PAID)
    make_order("TUP-1002", meera, OrderStatus.READY, PaymentStatus.PAID)
    make_order("TUP-1003", meera, OrderStatus.PENDING_PAYMENT, PaymentStatus.PENDING)
    return {"aarav": aarav, "meera": meera}


def numbers(response):
    return sorted(row["order_number"] for row in response.get_json()["data"]["orders"])


def test_search_matches_student_name_case_insensitively(app, seeded):
    client = client_for_admin(app)
    assert numbers(client.get("/api/admin/orders?q=meera")) == ["TUP-1002", "TUP-1003"]
    assert numbers(client.get("/api/admin/orders?q=AARAV")) == ["TUP-1001"]


def test_search_matches_email_and_order_number(app, seeded):
    client = client_for_admin(app)
    assert numbers(client.get("/api/admin/orders?q=aarav@test")) == ["TUP-1001"]
    assert numbers(client.get("/api/admin/orders?q=1002")) == ["TUP-1002"]


def test_search_treats_wildcards_as_plain_text(app, seeded):
    client = client_for_admin(app)
    assert numbers(client.get("/api/admin/orders?q=%25")) == []
    assert numbers(client.get("/api/admin/orders?q=_")) == []


def test_search_combines_with_status_and_payment_filters(app, seeded):
    client = client_for_admin(app)
    response = client.get("/api/admin/orders?q=meera&payment_status=pending")
    assert numbers(response) == ["TUP-1003"]

    response = client.get("/api/admin/orders?q=meera&order_status=ready")
    assert numbers(response) == ["TUP-1002"]


def test_search_is_paginated_on_the_server(app, seeded):
    client = client_for_admin(app)
    response = client.get("/api/admin/orders?q=meera&per_page=1&page=2")
    body = response.get_json()["data"]
    assert len(body["orders"]) == 1
    assert body["pagination"]["total"] == 2
    assert body["pagination"]["page"] == 2


def test_each_order_includes_student_details(app, seeded):
    client = client_for_admin(app)
    row = next(o for o in client.get("/api/admin/orders?q=TUP-1001").get_json()["data"]["orders"])
    assert row["student"]["name"] == "Aarav Shah"
    assert row["total_paise"] == 10000


def test_overlong_or_blank_search(app, seeded):
    client = client_for_admin(app)
    too_long = client.get("/api/admin/orders?q=" + "a" * 101)
    assert too_long.status_code == 400
    assert too_long.get_json()["error"]["code"] == "INVALID_FILTER"

    blank = client.get("/api/admin/orders?q=%20%20")
    assert blank.status_code == 200
    assert numbers(blank) == ["TUP-1001", "TUP-1002", "TUP-1003"]
