from datetime import datetime, timezone

from sqlalchemy import JSON

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class MenuItem(db.Model):
    __tablename__ = "menu_items"

    __table_args__ = (
        db.CheckConstraint("price_paise >= 0", name="ck_menu_items_price_non_negative"),
        db.CheckConstraint(
            "stock_quantity IS NULL OR stock_quantity >= 0",
            name="ck_menu_items_stock_non_negative",
        ),
        db.CheckConstraint("reserved_quantity >= 0", name="ck_menu_items_reserved_non_negative"),
        # Held units can never exceed the stock on hand.
        db.CheckConstraint(
            "stock_quantity IS NULL OR reserved_quantity <= stock_quantity",
            name="ck_menu_items_reserved_within_stock",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(60), nullable=False, index=True)

    # Integer paise only (₹1 = 100 paise). Never use floats for money.
    price_paise = db.Column(db.Integer, nullable=False)

    image_url = db.Column(db.String(500), nullable=True)
    is_available = db.Column(db.Boolean, nullable=False, default=True)

    # Diet is None when the canteen has not recorded it. Such items are not listed under
    # either the veg or non-veg filter.
    is_veg = db.Column(db.Boolean, nullable=True)
    ingredients = db.Column(JSON, nullable=True)
    preparation = db.Column(db.Text, nullable=True)
    recipe_steps = db.Column(JSON, nullable=True)

    # NULL means the item is not stock-tracked.
    stock_quantity = db.Column(db.Integer, nullable=True)

    # Units held by orders that are waiting for payment. Always 0 for untracked items.
    # Available stock = stock_quantity - reserved_quantity.
    reserved_quantity = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
