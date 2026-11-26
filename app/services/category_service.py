from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.menu import MenuItem
from app.models.menu_category import MenuCategory
from app.services.errors import ConflictError, ServiceValidationError

NAME_MAX_LENGTH = 60  # Matches MenuItem.category.


def _validated_name(data):
    value = data.get("name") if isinstance(data, dict) else None
    if not isinstance(value, str):
        raise ServiceValidationError({"name": "Must be a string."})
    value = value.strip()
    if not value:
        raise ServiceValidationError({"name": "Cannot be empty."})
    if len(value) > NAME_MAX_LENGTH:
        raise ServiceValidationError({"name": f"Must be at most {NAME_MAX_LENGTH} characters."})
    return value


def _name_taken(name, exclude_id=None):
    # Case-insensitive, so "Snacks" and "snacks" can't both exist.
    query = MenuCategory.query.filter(func.lower(MenuCategory.name) == name.lower())
    if exclude_id is not None:
        query = query.filter(MenuCategory.id != exclude_id)
    return query.first() is not None


def _duplicate_error():
    return ConflictError("CATEGORY_EXISTS", "A category with this name already exists.")


def item_count(name):
    return MenuItem.query.filter_by(category=name).count()


def list_categories():
    """Return (category, number of menu items in it) pairs, sorted by name."""
    counts = dict(
        db.session.query(MenuItem.category, func.count(MenuItem.id))
        .group_by(MenuItem.category)
        .all()
    )
    categories = MenuCategory.query.order_by(MenuCategory.name, MenuCategory.id).all()
    return [(category, counts.get(category.name, 0)) for category in categories]


def serialize_category(category, count):
    return {
        "id": category.id,
        "name": category.name,
        "item_count": count,
        "created_at": category.created_at.isoformat() if category.created_at else None,
        "updated_at": category.updated_at.isoformat() if category.updated_at else None,
    }


def create_category(data):
    name = _validated_name(data)
    if _name_taken(name):
        raise _duplicate_error()
    category = MenuCategory(name=name)
    db.session.add(category)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise _duplicate_error()
    return category


def rename_category(category, data):
    """Rename a category and move every menu item in it to the new name, in one transaction."""
    name = _validated_name(data)
    if name == category.name:
        return category
    if _name_taken(name, exclude_id=category.id):
        raise _duplicate_error()

    old_name = category.name
    MenuItem.query.filter_by(category=old_name).update(
        {"category": name}, synchronize_session=False
    )
    category.name = name
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise _duplicate_error()
    return category


def delete_category(category):
    in_use = item_count(category.name)
    if in_use:
        raise ConflictError(
            "CATEGORY_IN_USE",
            f"{in_use} menu item(s) still use this category. Move or delete them first.",
        )
    db.session.delete(category)
    db.session.commit()
