from flask import current_app
from datetime import timedelta

from sqlalchemy import func, or_

from app.extensions import db
from app.models.menu import MenuItem
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.services.time_utils import utcnow
from app.security.url_rules import image_url_problem

NAME_MAX_LENGTH = 120
CATEGORY_MAX_LENGTH = 60
DESCRIPTION_MAX_LENGTH = 500
IMAGE_URL_MAX_LENGTH = 500
MAX_PRICE_PAISE = 1_000_000
MAX_STOCK_QUANTITY = 100_000
INGREDIENT_MAX_COUNT = 40
INGREDIENT_MAX_LENGTH = 120
RECIPE_STEP_MAX_COUNT = 40
RECIPE_STEP_MAX_LENGTH = 400
PREPARATION_MAX_LENGTH = 1000
POPULARITY_PERIODS = ("day", "week", "month")
POPULAR_LIMIT = 20
# Only orders that were actually placed count toward popularity. Unpaid and cancelled orders don't.
COUNTED_ORDER_STATUSES = (
    OrderStatus.RECEIVED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.COLLECTED,
)
ALLOWED_FIELDS = frozenset({
    "name", "description", "category", "price_paise",
    "image_url", "is_available", "stock_quantity",
    "is_veg", "ingredients", "preparation", "recipe_steps",
})


class MenuValidationError(ValueError):
    def __init__(self, errors):
        super().__init__("Menu item validation failed.")
        self.errors = errors


def _plain_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _text(field, value, max_length, errors, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str):
        errors[field] = "Must be a string."
        return None
    value = value.strip()
    if not value:
        if optional:
            return None
        errors[field] = "Cannot be empty."
        return None
    if len(value) > max_length:
        errors[field] = f"Must be at most {max_length} characters."
        return None
    return value


def _text_list(field, value, max_count, max_length, errors):
    if value is None:
        return []
    if not isinstance(value, list):
        errors[field] = "Must be a list of text entries."
        return None
    if len(value) > max_count:
        errors[field] = f"Must have at most {max_count} entries."
        return None
    cleaned = []
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            errors[field] = "Every entry must be non-empty text."
            return None
        entry = entry.strip()
        if len(entry) > max_length:
            errors[field] = f"Each entry must be at most {max_length} characters."
            return None
        cleaned.append(entry)
    return cleaned


def validate_menu_payload(data, partial=False):
    if partial and not data:
        raise MenuValidationError({"body": "Provide at least one field to update."})

    errors = {}
    cleaned = {}
    unknown = sorted(set(data) - ALLOWED_FIELDS)
    if unknown:
        errors["unknown_fields"] = f"Unsupported fields: {', '.join(unknown)}."

    if "name" in data:
        cleaned["name"] = _text("name", data["name"], NAME_MAX_LENGTH, errors)
    elif not partial:
        errors["name"] = "This field is required."

    if "category" in data:
        cleaned["category"] = _text("category", data["category"], CATEGORY_MAX_LENGTH, errors)
    elif not partial:
        errors["category"] = "This field is required."

    if "description" in data:
        cleaned["description"] = _text("description", data["description"], DESCRIPTION_MAX_LENGTH, errors, optional=True)

    if "price_paise" in data:
        value = data["price_paise"]
        if _plain_int(value) and 0 <= value <= MAX_PRICE_PAISE:
            cleaned["price_paise"] = value
        else:
            errors["price_paise"] = f"Must be a whole number of paise from 0 to {MAX_PRICE_PAISE}."
    elif not partial:
        errors["price_paise"] = "This field is required."

    if "image_url" in data:
        value = _text("image_url", data["image_url"], IMAGE_URL_MAX_LENGTH, errors, optional=True)
        if value is not None:
            problem = image_url_problem(value, current_app.config.get("MENU_IMAGE_ALLOWED_HOSTS", ()))
            if problem:
                errors["image_url"] = problem
        cleaned["image_url"] = value

    if "is_available" in data:
        value = data["is_available"]
        if isinstance(value, bool):
            cleaned["is_available"] = value
        else:
            errors["is_available"] = "Must be true or false."
    elif not partial:
        cleaned["is_available"] = True

    if "stock_quantity" in data:
        value = data["stock_quantity"]
        if value is None or (_plain_int(value) and 0 <= value <= MAX_STOCK_QUANTITY):
            cleaned["stock_quantity"] = value
        else:
            errors["stock_quantity"] = f"Must be empty or a whole number from 0 to {MAX_STOCK_QUANTITY}."

    if "is_veg" in data:
        value = data["is_veg"]
        if value is None or isinstance(value, bool):
            cleaned["is_veg"] = value
        else:
            errors["is_veg"] = "Must be true, false or null (not recorded)."

    if "ingredients" in data:
        cleaned["ingredients"] = _text_list(
            "ingredients", data["ingredients"], INGREDIENT_MAX_COUNT, INGREDIENT_MAX_LENGTH, errors
        )

    if "recipe_steps" in data:
        cleaned["recipe_steps"] = _text_list(
            "recipe_steps", data["recipe_steps"], RECIPE_STEP_MAX_COUNT, RECIPE_STEP_MAX_LENGTH, errors
        )

    if "preparation" in data:
        cleaned["preparation"] = _text(
            "preparation", data["preparation"], PREPARATION_MAX_LENGTH, errors, optional=True
        )

    if errors:
        raise MenuValidationError(errors)
    return cleaned


def serialize_menu_item(item):
    available = None
    if item.stock_quantity is not None:
        available = max(item.stock_quantity - item.reserved_quantity, 0)
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "category": item.category,
        "price_paise": item.price_paise,
        "image_url": item.image_url,
        "is_available": item.is_available,
        "is_veg": item.is_veg,
        "ingredients": item.ingredients or [],
        "preparation": item.preparation,
        "recipe_steps": item.recipe_steps or [],
        "stock_quantity": item.stock_quantity,
        "reserved_quantity": item.reserved_quantity,
        "available_quantity": available,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def is_orderable(item):
    """Available for ordering right now: switched on, and not sold out."""
    if not item.is_available:
        return False
    return item.stock_quantity is None or item.stock_quantity > item.reserved_quantity


def serialize_public_menu_item(item):
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "category": item.category,
        "price_paise": item.price_paise,
        "image_url": item.image_url,
        "is_veg": item.is_veg,
        "ingredients": item.ingredients or [],
        "preparation": item.preparation,
        "recipe_steps": item.recipe_steps or [],
        "is_available": is_orderable(item),
    }


def list_public_menu_items():
    return (
        MenuItem.query
        .filter(MenuItem.is_available.is_(True))
        .filter(or_(
            MenuItem.stock_quantity.is_(None),
            MenuItem.stock_quantity > MenuItem.reserved_quantity,
        ))
        .order_by(MenuItem.category, MenuItem.name, MenuItem.id)
        .all()
    )


def create_menu_item(data):
    cleaned = validate_menu_payload(data, partial=False)
    item = MenuItem(**cleaned)
    db.session.add(item)
    db.session.commit()
    return item


def update_menu_item(item, data):
    cleaned = validate_menu_payload(data, partial=True)
    if "stock_quantity" in cleaned:
        new_stock = cleaned["stock_quantity"]
        held = item.reserved_quantity or 0
        if new_stock is None and held:
            raise MenuValidationError({
                "stock_quantity": "Cannot disable stock tracking while units are reserved."
            })
        if new_stock is not None and new_stock < held:
            raise MenuValidationError({
                "stock_quantity": f"Cannot set stock below the {held} unit(s) already reserved."
            })
    for field, value in cleaned.items():
        setattr(item, field, value)
    db.session.commit()
    return item


def get_public_menu_item(item_id):
    """Return any menu item by id, including ones that are currently unavailable."""
    return db.session.get(MenuItem, item_id)


def period_start(period):
    """Start of the popularity window. "day" starts at local midnight at the canteen."""
    now = utcnow()
    if period == "day":
        offset = timedelta(minutes=current_app.config["CANTEEN_UTC_OFFSET_MINUTES"])
        local_midnight = (now + offset).replace(hour=0, minute=0, second=0, microsecond=0)
        return local_midnight - offset
    return now - timedelta(days=7 if period == "week" else 30)


def popular_menu_items(period):
    """Most-ordered items in the period, by quantity, from orders that were actually placed."""
    if period not in POPULARITY_PERIODS:
        raise ValueError(f"Unknown popularity period: {period}")
    rows = (
        db.session.query(OrderItem.menu_item_id, func.sum(OrderItem.quantity))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            OrderItem.menu_item_id.isnot(None),
            Order.created_at >= period_start(period),
            Order.order_status.in_(COUNTED_ORDER_STATUSES),
        )
        .group_by(OrderItem.menu_item_id)
        .order_by(func.sum(OrderItem.quantity).desc(), OrderItem.menu_item_id)
        .limit(POPULAR_LIMIT)
        .all()
    )
    return [{"menu_item_id": item_id, "quantity": int(quantity)} for item_id, quantity in rows]
