"""Stock holds and sales.

Lifecycle of a tracked item in one order:

    create order   -> reserve_stock       reserved += qty    (reservation: RESERVED)
    payment ok     -> commit_reservations stock -= qty, reserved -= qty  (COMMITTED)
    expired/cancel -> release_reservations reserved -= qty    (RELEASED)
    cancel paid    -> return_sold_stock   stock += qty       (RELEASED)

Every change is a conditional UPDATE, so stock can never go negative and two
orders can never both take the last unit. All functions run inside the caller's
transaction and do not commit.
"""

from app.extensions import db
from app.models.menu import MenuItem
from app.models.stock_reservation import ReservationStatus, StockReservation
from app.services.errors import OrderError


def _inventory_mismatch():
    return OrderError(
        "INVENTORY_MISMATCH",
        "Stock no longer matches the orders for this item. Flag it for review.",
        409,
    )


def _units_left(menu_item_id):
    """Units available right now, read straight from the database (not the session cache)."""
    row = (
        db.session.query(MenuItem.stock_quantity, MenuItem.reserved_quantity)
        .filter(MenuItem.id == menu_item_id)
        .first()
    )
    if row is None or row[0] is None:
        return 0
    return max(row[0] - row[1], 0)


def reserve_stock(order_id, lines):
    """Hold stock for an unpaid order. `lines` are PricedLine objects from pricing_service."""
    for line in lines:
        if not line.stock_tracked:
            continue

        updated = (
            MenuItem.query.filter(
                MenuItem.id == line.menu_item_id,
                MenuItem.stock_quantity.isnot(None),
                MenuItem.stock_quantity - MenuItem.reserved_quantity >= line.quantity,
            ).update(
                {MenuItem.reserved_quantity: MenuItem.reserved_quantity + line.quantity},
                synchronize_session=False,
            )
        )
        if updated != 1:
            # Another order took the units between the pricing check and now.
            left = _units_left(line.menu_item_id)
            if left <= 0:
                raise OrderError(
                    "INSUFFICIENT_STOCK",
                    f"'{line.item_name}' is sold out right now.",
                    409,
                )
            raise OrderError(
                "INSUFFICIENT_STOCK",
                f"Only {left} of '{line.item_name}' left.",
                409,
            )

        db.session.add(StockReservation(
            order_id=order_id,
            menu_item_id=line.menu_item_id,
            quantity=line.quantity,
            status=ReservationStatus.RESERVED,
        ))


def commit_reservations(order_id):
    """Payment confirmed: the held units become sold. Stock and hold drop together."""
    reservations = StockReservation.query.filter_by(
        order_id=order_id,
        status=ReservationStatus.RESERVED,
    ).all()

    for reservation in reservations:
        updated = (
            MenuItem.query.filter(
                MenuItem.id == reservation.menu_item_id,
                MenuItem.stock_quantity >= reservation.quantity,
                MenuItem.reserved_quantity >= reservation.quantity,
            ).update(
                {
                    MenuItem.stock_quantity: MenuItem.stock_quantity - reservation.quantity,
                    MenuItem.reserved_quantity: MenuItem.reserved_quantity - reservation.quantity,
                },
                synchronize_session=False,
            )
        )
        if updated != 1:
            raise _inventory_mismatch()
        reservation.status = ReservationStatus.COMMITTED


def release_reservations(order_id):
    """Unpaid order expired or was cancelled: give the held units back."""
    reservations = StockReservation.query.filter_by(
        order_id=order_id,
        status=ReservationStatus.RESERVED,
    ).all()

    for reservation in reservations:
        updated = (
            MenuItem.query.filter(
                MenuItem.id == reservation.menu_item_id,
                MenuItem.reserved_quantity >= reservation.quantity,
            ).update(
                {MenuItem.reserved_quantity: MenuItem.reserved_quantity - reservation.quantity},
                synchronize_session=False,
            )
        )
        if updated != 1:
            raise _inventory_mismatch()
        reservation.status = ReservationStatus.RELEASED


def return_sold_stock(order_id):
    """Paid order was cancelled: put its sold units back on the shelf."""
    reservations = StockReservation.query.filter_by(
        order_id=order_id,
        status=ReservationStatus.COMMITTED,
    ).all()

    for reservation in reservations:
        updated = (
            MenuItem.query.filter(
                MenuItem.id == reservation.menu_item_id,
                MenuItem.stock_quantity.isnot(None),
            ).update(
                {MenuItem.stock_quantity: MenuItem.stock_quantity + reservation.quantity},
                synchronize_session=False,
            )
        )
        if updated != 1:
            raise _inventory_mismatch()
