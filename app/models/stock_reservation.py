from app.extensions import db
from app.models.order import utcnow


class ReservationStatus:
    RESERVED = "reserved"    # Held while the order waits for payment
    COMMITTED = "committed"  # Payment confirmed: the units are sold
    RELEASED = "released"    # Hold removed (order expired or cancelled), or sold units returned


class StockReservation(db.Model):
    __tablename__ = "stock_reservations"

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_stock_reservations_quantity_positive"),
        # An order lists each menu item at most once, so it has at most one reservation per item.
        db.UniqueConstraint("order_id", "menu_item_id", name="uq_stock_reservations_order_item"),
    )

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    menu_item_id = db.Column(
        db.Integer,
        db.ForeignKey("menu_items.id"),
        nullable=False,
        index=True,
    )

    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(
        db.String(20),
        nullable=False,
        default=ReservationStatus.RESERVED,
        index=True,
    )

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
