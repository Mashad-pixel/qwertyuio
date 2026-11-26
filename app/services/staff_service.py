"""Staff accounts (ADMIN and KITCHEN). Only administrators can call these functions.

Students are never managed here. Every change is written in one transaction, and the rules below
prevent an administrator from locking everyone out.
"""

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.user import User, UserRole
from app.security.account_rules import is_valid_email, is_valid_name, normalize_email, password_problem
from app.services.errors import OrderError, ServiceValidationError

STAFF_ROLES = (UserRole.ADMIN, UserRole.KITCHEN)
ASSIGNABLE_ROLES = {"ADMIN": UserRole.ADMIN, "KITCHEN": UserRole.KITCHEN}
CREATE_FIELDS = frozenset({"name", "email", "password", "role"})
UPDATE_FIELDS = frozenset({"name", "role", "is_active"})


def serialize_staff(user):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def list_staff():
    return User.query.filter(User.role.in_(STAFF_ROLES)).order_by(User.name, User.id).all()


def get_staff(user_id):
    user = db.session.get(User, user_id)
    if user is None or user.role not in STAFF_ROLES:
        raise OrderError("STAFF_NOT_FOUND", "Staff account not found.", 404)
    return user


def _unknown_fields(data, allowed):
    unknown = sorted(set(data) - allowed)
    return {"unknown_fields": f"Unsupported fields: {', '.join(unknown)}."} if unknown else {}


def _role_value(raw, errors):
    if not isinstance(raw, str) or raw.upper() not in ASSIGNABLE_ROLES:
        errors["role"] = "Must be ADMIN or KITCHEN."
        return None
    return ASSIGNABLE_ROLES[raw.upper()]


def create_staff(data, actor):
    errors = _unknown_fields(data, CREATE_FIELDS)
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    role = None

    if not isinstance(name, str) or not is_valid_name(name.strip()):
        errors["name"] = "Enter a name (up to 100 characters)."
    if not isinstance(email, str) or not is_valid_email(normalize_email(email)):
        errors["email"] = "Enter a valid email address."
    if not isinstance(password, str):
        errors["password"] = "Enter a password."
    else:
        problem = password_problem(password)
        if problem:
            errors["password"] = problem
    if "role" not in data:
        errors["role"] = "This field is required."
    else:
        role = _role_value(data["role"], errors)

    if errors:
        raise ServiceValidationError(errors, "Staff account is invalid.")

    email = normalize_email(email)
    if User.query.filter_by(email=email).first() is not None:
        raise OrderError("EMAIL_UNAVAILABLE", "An account with this email already exists.", 409)

    user = User(name=" ".join(name.split()), email=email, role=role, is_active=True)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise OrderError("EMAIL_UNAVAILABLE", "An account with this email already exists.", 409)

    current_app.logger.info("staff account %s (%s) created by user %s", user.id, role, actor.id)
    return user


def update_staff(user, data, actor):
    if not data:
        raise ServiceValidationError({"body": "Provide at least one field to update."}, "Staff update is invalid.")
    errors = _unknown_fields(data, UPDATE_FIELDS)

    new_name = user.name
    new_role = user.role
    new_active = user.is_active

    if "name" in data:
        if not isinstance(data["name"], str) or not is_valid_name(data["name"].strip()):
            errors["name"] = "Enter a name (up to 100 characters)."
        else:
            new_name = " ".join(data["name"].split())
    if "role" in data:
        parsed = _role_value(data["role"], errors)
        if parsed is not None:
            new_role = parsed
    if "is_active" in data:
        if isinstance(data["is_active"], bool):
            new_active = data["is_active"]
        else:
            errors["is_active"] = "Must be true or false."

    if errors:
        raise ServiceValidationError(errors, "Staff update is invalid.")

    changes_access = new_role != user.role or new_active != user.is_active
    if user.id == actor.id and changes_access:
        raise OrderError(
            "SELF_CHANGE_NOT_ALLOWED",
            "You cannot change your own role or deactivate your own account.",
            409,
        )

    was_active_admin = user.role == UserRole.ADMIN and user.is_active
    stays_active_admin = new_role == UserRole.ADMIN and new_active
    if was_active_admin and not stays_active_admin:
        other_admins = User.query.filter(
            User.role == UserRole.ADMIN,
            User.is_active.is_(True),
            User.id != user.id,
        ).count()
        if other_admins == 0:
            raise OrderError("LAST_ADMIN", "At least one active administrator must remain.", 409)

    user.name = new_name
    user.role = new_role
    user.is_active = new_active
    db.session.commit()
    current_app.logger.info(
        "staff account %s updated by user %s (role=%s active=%s)",
        user.id, actor.id, user.role, user.is_active,
    )
    return user
