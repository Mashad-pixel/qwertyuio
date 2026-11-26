from app.extensions import db
from app.models.canteen import CanteenSettings
from app.security.admin_rules import CANTEEN_NAME_MAX_LENGTH, check_hours_pair, clean_canteen_name, clean_hhmm
from app.services.errors import ServiceValidationError

SINGLETON_ID = 1
CLOSED_MESSAGE_MAX_LENGTH = 200
DEFAULT_CANTEEN_NAME = "TrayUP Canteen"
ALLOWED_FIELDS = frozenset({"is_accepting_orders", "closed_message"})
DETAIL_FIELDS = frozenset({"canteen_name", "opens_at", "closes_at"})


def _settings_row():
    return db.session.get(CanteenSettings, SINGLETON_ID)


def _details(settings):
    if settings is None:
        return {"canteen_name": DEFAULT_CANTEEN_NAME, "opens_at": None, "closes_at": None}
    return {
        "canteen_name": settings.canteen_name,
        "opens_at": settings.opens_at,
        "closes_at": settings.closes_at,
    }


def get_status():
    """The canteen is open unless an admin has explicitly closed it. Name and hours are public."""
    settings = _settings_row()
    details = _details(settings)
    if settings is None or settings.is_accepting_orders:
        return {"is_accepting_orders": True, "message": None, **details}
    return {"is_accepting_orders": False, "message": settings.closed_message, **details}


def is_accepting_orders():
    return get_status()["is_accepting_orders"]


def get_settings():
    """Every canteen setting an administrator can edit."""
    settings = _settings_row()
    status = get_status()
    return {
        **_details(settings),
        "is_accepting_orders": status["is_accepting_orders"],
        "closed_message": status["message"],
    }


def update_details(data):
    """Change the name and/or hours. Only the fields present in data are changed."""
    errors = {}
    unknown = sorted(set(data) - DETAIL_FIELDS)
    if unknown:
        errors["unknown_fields"] = f"Unsupported fields: {', '.join(unknown)}."
    if not data:
        errors["body"] = "Provide at least one field to update."

    current = _settings_row()
    current_details = _details(current)
    name = current_details["canteen_name"]
    opens_at = current_details["opens_at"]
    closes_at = current_details["closes_at"]

    if "canteen_name" in data:
        try:
            name = clean_canteen_name(data["canteen_name"])
        except ValueError as exc:
            errors["canteen_name"] = str(exc)
    if "opens_at" in data:
        try:
            opens_at = clean_hhmm(data["opens_at"])
        except ValueError as exc:
            errors["opens_at"] = str(exc)
    if "closes_at" in data:
        try:
            closes_at = clean_hhmm(data["closes_at"])
        except ValueError as exc:
            errors["closes_at"] = str(exc)

    if not errors:
        problem = check_hours_pair(opens_at, closes_at)
        if problem:
            errors["hours"] = problem

    if errors:
        raise ServiceValidationError(errors, "Canteen details are invalid.")

    settings = current
    if settings is None:
        settings = CanteenSettings(id=SINGLETON_ID)
        db.session.add(settings)
    settings.canteen_name = name
    settings.opens_at = opens_at
    settings.closes_at = closes_at
    db.session.commit()
    return get_settings()


def update_status(data):
    errors = {}
    unknown = sorted(set(data) - ALLOWED_FIELDS)
    if unknown:
        errors["unknown_fields"] = f"Unsupported fields: {', '.join(unknown)}."

    if "is_accepting_orders" not in data:
        errors["is_accepting_orders"] = "This field is required."
    elif not isinstance(data["is_accepting_orders"], bool):
        errors["is_accepting_orders"] = "Must be true or false."

    message = data.get("closed_message")
    if message is not None and not isinstance(message, str):
        errors["closed_message"] = "Must be a string."
    elif isinstance(message, str) and len(message.strip()) > CLOSED_MESSAGE_MAX_LENGTH:
        errors["closed_message"] = f"Must be at most {CLOSED_MESSAGE_MAX_LENGTH} characters."

    if errors:
        raise ServiceValidationError(errors, "Canteen status update is invalid.")

    is_open = data["is_accepting_orders"]
    cleaned_message = message.strip() if isinstance(message, str) and message.strip() else None

    settings = _settings_row()
    if settings is None:
        settings = CanteenSettings(id=SINGLETON_ID)
        db.session.add(settings)
    settings.is_accepting_orders = is_open
    settings.closed_message = None if is_open else cleaned_message
    db.session.commit()
    return get_status()
