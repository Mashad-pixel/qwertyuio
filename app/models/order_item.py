from app.extensions import db
from app.models.order import utcnow


class OrderItem(db.Model):
    __tablename__ = "order_items"

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        db.CheckConstraint("unit_price_snapshot_paise >= 0", name="ck_order_items_price_non_negative"),
        db.CheckConstraint(
            "line_total_paise = unit_price_snapshot_paise * quantity",
            name="ck_order_items_line_total_matches",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # SET NULL keeps order history if a menu item is later deleted.
    menu_item_id = db.Column(
        db.Integer,
        db.ForeignKey("menu_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Snapshots taken at purchase time, so old receipts don't change when the menu changes.
    item_name_snapshot = db.Column(db.String(120), nullable=False)
    unit_price_snapshot_paise = db.Column(db.Integer, nullable=False)

    quantity = db.Column(db.Integer, nullable=False)
    line_total_paise = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    order = db.relationship("Order", back_populates="items")
