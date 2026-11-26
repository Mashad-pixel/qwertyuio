from app.extensions import db
from app.models.order import utcnow


class MenuCategory(db.Model):
    """A category a menu item can belong to.

    MenuItem.category stores the name as text, so renaming a category has to update those items
    too (see category_service.rename_category). The name is unique, matching the menu_items data.
    """

    __tablename__ = "menu_categories"

    __table_args__ = (
        db.UniqueConstraint("name", name="uq_menu_categories_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
