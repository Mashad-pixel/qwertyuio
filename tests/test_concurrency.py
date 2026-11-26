"""Stress tests: many threads hit the same stock, order and collection-code rows at once.

By default these run on a temporary SQLite file. Set TRAYUP_STRESS_DATABASE_URL to run the same
tests against PostgreSQL, which is what production uses (row locks, FOR UPDATE, SKIP LOCKED):

    TRAYUP_STRESS_DATABASE_URL=postgresql+psycopg://user:pass@localhost/trayup_stress pytest tests/test_concurrency.py

The database is emptied at the start and end of each test, so use a database that nothing else uses.

Each worker runs in its own app context, so it has its own session and its own transactions.
A barrier releases every worker at the same moment so the work actually overlaps.
"""
import hashlib
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models.collection_token import CollectionToken
from app.models.menu import MenuItem
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.order_status_history import OrderStatusHistory
from app.models.stock_reservation import ReservationStatus, StockReservation
from app.models.user import User, UserRole
from app.services.collection_service import confirm_collection, get_student_collection_qr, preview_collection
from app.services.errors import OrderError
from app.services.kitchen_service import change_order_status
from app.services.order_service import cancel_order, create_order, expire_unpaid_orders
from app.services.time_utils import as_utc
from tests.test_reports import pay

STRESS_DATABASE_URL = os.getenv("TRAYUP_STRESS_DATABASE_URL", "").strip()
WORKERS = 12


# ---------- Setup ----------

def _serialize_sqlite_writes(engine):
    """Start every SQLite transaction with BEGIN IMMEDIATE (the SQLAlchemy pysqlite recipe).

    With the default driver behaviour, two connections that both read and then write can fail
    at once with 'database is locked', without waiting. Taking the write lock up front makes SQLite
    queue the transactions instead, which is how production behaves. Used only by these tests.
    """

    @event.listens_for(engine, "connect")
    def _no_implicit_begin(dbapi_connection, _record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin_immediate(connection):
        connection.exec_driver_sql("BEGIN IMMEDIATE")


@pytest.fixture
def stress_app(tmp_path, monkeypatch):
    url = STRESS_DATABASE_URL or f"sqlite:///{tmp_path / 'stress.db'}"
    if url.startswith("sqlite"):
        engine_options = {"connect_args": {"timeout": 30}, "pool_size": WORKERS + 4, "max_overflow": 0}
    else:
        engine_options = {"pool_size": WORKERS + 4, "max_overflow": 0, "pool_timeout": 60}

    monkeypatch.setattr(TestingConfig, "SQLALCHEMY_DATABASE_URI", url)
    monkeypatch.setattr(TestingConfig, "SQLALCHEMY_ENGINE_OPTIONS", engine_options, raising=False)

    app = create_app("testing")
    with app.app_context():
        if url.startswith("sqlite"):
            _serialize_sqlite_writes(db.engine)
        db.session.remove()
        db.drop_all()
        db.create_all()
        try:
            yield app
        finally:
            db.session.remove()
            db.drop_all()
            db.engine.dispose()


def make_user(email, role, name="Stress User"):
    user = User(name=name, email=email, role=role, is_active=True)
    user.set_password("StrongPass123!")
    db.session.add(user)
    db.session.commit()
    return user.id


def run_in_threads(app, jobs):
    """Run each (function, args) job at the same moment, each in its own app context.

    Returns one ("ok", value) / ("order_error", code) / ("crash", description) per job. Workers
    must return plain values, not ORM objects, because each worker's session is closed afterwards.
    """
    barrier = threading.Barrier(len(jobs))

    def runner(job):
        function, args = job
        with app.app_context():
            try:
                barrier.wait(timeout=60)
                return ("ok", function(*args))
            except OrderError as exc:
                return ("order_error", exc.code)
            except Exception as exc:  # noqa: BLE001 - an unexpected failure is exactly what we are looking for
                return ("crash", f"{type(exc).__name__}: {exc}")
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [pool.submit(runner, job) for job in jobs]
        return [future.result(timeout=300) for future in futures]


def kinds(results):
    return [kind for kind, _ in results]


def sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------- Item 46: stock reservations under simultaneous ordering ----------

def _place_order(student_id, menu_item_id, quantity):
    order, _ = create_order(student_id, [{"menu_item_id": menu_item_id, "quantity": quantity}])
    return order.id


def test_simultaneous_orders_for_the_last_units_never_oversell(stress_app):
    app = stress_app
    with app.app_context():
        item = MenuItem(
            name="Paneer Roll", category="Meals", price_paise=6000,
            is_available=True, stock_quantity=5,
        )
        db.session.add(item)
        db.session.commit()
        item_id = item.id
        student_ids = [make_user(f"buyer{i}@test.com", UserRole.STUDENT, f"Buyer {i}") for i in range(WORKERS)]

    results = run_in_threads(app, [(_place_order, (sid, item_id, 1)) for sid in student_ids])

    assert "crash" not in kinds(results), results
    won = [value for kind, value in results if kind == "ok"]
    lost = [code for kind, code in results if kind == "order_error"]
    assert len(won) == 5
    assert len(set(won)) == 5
    assert lost == ["INSUFFICIENT_STOCK"] * (WORKERS - 5)

    with app.app_context():
        item = db.session.get(MenuItem, item_id)
        assert (item.stock_quantity, item.reserved_quantity) == (5, 5)
        held = StockReservation.query.filter_by(menu_item_id=item_id, status=ReservationStatus.RESERVED).all()
        assert sum(row.quantity for row in held) == 5
        assert Order.query.count() == 5  # losers' orders were rolled back, not left half-made


def _mixed_traffic_worker(app, student_id, staff_id, menu_item_id, seed):
    rng = random.Random(seed)
    mine = []
    for _ in range(8):
        roll = rng.random()
        try:
            if roll < 0.6 or not mine:
                mine.append(_place_order(student_id, menu_item_id, rng.randint(1, 2)))
            elif roll < 0.85:
                cancel_order(rng.choice(mine), staff_id, "stress test cancel")
            else:
                expire_unpaid_orders()
        except OrderError:
            pass  # sold out, already cancelled, etc. are normal outcomes under contention
    return len(mine)


def test_mixed_orders_cancels_and_expiry_keep_stock_consistent(stress_app):
    app = stress_app
    # A zero-minute payment window makes every unpaid order overdue at once. Creating an order
    # then races with expiring other students' orders, which is the hardest case to get right.
    app.config["ORDER_PAYMENT_EXPIRY_MINUTES"] = 0
    with app.app_context():
        item = MenuItem(
            name="Samosa", category="Snacks", price_paise=1500,
            is_available=True, stock_quantity=6,
        )
        db.session.add(item)
        db.session.commit()
        item_id = item.id
        staff_id = make_user("stress-admin@test.com", UserRole.ADMIN, "Stress Admin")
        student_ids = [make_user(f"mix{i}@test.com", UserRole.STUDENT, f"Mix {i}") for i in range(WORKERS)]

    jobs = [
        (_mixed_traffic_worker, (app, sid, staff_id, item_id, 1000 + index))
        for index, sid in enumerate(student_ids)
    ]
    results = run_in_threads(app, jobs)
    assert "crash" not in kinds(results), results

    with app.app_context():
        item = db.session.get(MenuItem, item_id)
        held_units = (
            db.session.query(db.func.coalesce(db.func.sum(StockReservation.quantity), 0))
            .filter(StockReservation.menu_item_id == item_id, StockReservation.status == ReservationStatus.RESERVED)
            .scalar()
        )
        assert item.stock_quantity == 6  # nothing was paid, so no units were sold
        assert item.reserved_quantity == held_units
        assert 0 <= item.reserved_quantity <= item.stock_quantity

        # Every hold belongs to an order still waiting for payment.
        for reservation in StockReservation.query.filter_by(status=ReservationStatus.RESERVED).all():
            order = db.session.get(Order, reservation.order_id)
            assert order.order_status == OrderStatus.PENDING_PAYMENT
            assert order.payment_status == PaymentStatus.PENDING


# ---------- Item 47: collection codes under simultaneous issuance, renewal and confirmation ----------

@pytest.fixture
def ready_order(stress_app):
    """A paid order that the kitchen has marked ready. Returns (app, order_id, student_id, staff_id)."""
    app = stress_app
    with app.app_context():
        item = MenuItem(
            name="Samosa", category="Snacks", price_paise=1500,
            is_available=True, stock_quantity=None,
        )
        db.session.add(item)
        db.session.commit()
        student = db.session.get(User, make_user("qr-student@test.com", UserRole.STUDENT, "QR Student"))
        staff_id = make_user("qr-kitchen@test.com", UserRole.KITCHEN, "QR Kitchen")
        order = pay(student, "samosa", {"samosa": item}, 1)
        change_order_status(order.id, "preparing", staff_id)
        change_order_status(order.id, "ready", staff_id)
        return app, order.id, student.id, staff_id


def _issue_code(order_id, student_id):
    raw, token, _order = get_student_collection_qr(order_id, student_id)
    return raw, as_utc(token.expires_at).isoformat()


def _confirm(raw, staff_id):
    return confirm_collection(raw, staff_id).id


def test_simultaneous_code_requests_all_get_a_working_code(ready_order):
    app, order_id, student_id, _staff_id = ready_order

    results = run_in_threads(app, [(_issue_code, (order_id, student_id)) for _ in range(WORKERS)])

    assert "crash" not in kinds(results), results
    issued = [value for kind, value in results if kind == "ok"]
    assert len(issued) == WORKERS
    with app.app_context():
        for raw, expires_at in issued:
            preview = preview_collection(raw)  # every code handed out must actually work
            assert preview.id == order_id
            row = CollectionToken.query.filter_by(token_hash=sha256(raw)).one()
            # The expiry returned with a code must be that code's own expiry, not another request's.
            assert as_utc(row.expires_at).isoformat() == expires_at
            assert row.used_at is None


def test_renewal_under_concurrency_issues_working_codes_after_expiry(ready_order):
    app, order_id, student_id, _staff_id = ready_order
    with app.app_context():
        get_student_collection_qr(order_id, student_id)  # issue an initial code
        CollectionToken.query.filter_by(order_id=order_id).update(
            {"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)},
            synchronize_session=False,
        )
        db.session.commit()

    results = run_in_threads(app, [(_issue_code, (order_id, student_id)) for _ in range(WORKERS)])

    assert "crash" not in kinds(results), results
    assert kinds(results) == ["ok"] * WORKERS
    with app.app_context():
        for _kind, (raw, expires_at) in results:
            preview_collection(raw)
            assert datetime.fromisoformat(expires_at) > datetime.now(timezone.utc)


def test_simultaneous_confirmations_collect_the_order_exactly_once(ready_order):
    app, order_id, student_id, staff_id = ready_order
    with app.app_context():
        raw, _expires_at = _issue_code(order_id, student_id)

    results = run_in_threads(app, [(_confirm, (raw, staff_id)) for _ in range(6)])

    assert "crash" not in kinds(results), results
    winners = [value for kind, value in results if kind == "ok"]
    losers = [code for kind, code in results if kind == "order_error"]
    assert winners == [order_id]
    assert len(losers) == 5
    assert set(losers) <= {"TOKEN_ALREADY_USED", "ORDER_NOT_READY"}

    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.order_status == OrderStatus.COLLECTED
        collected_rows = OrderStatusHistory.query.filter_by(
            order_id=order_id, new_status=OrderStatus.COLLECTED,
        ).count()
        assert collected_rows == 1
