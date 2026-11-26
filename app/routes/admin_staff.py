"""Staff accounts (ADMIN and KITCHEN), managed by administrators.

Students are managed through registration only. This API can never create, edit or disable
a student account. Every change that affects access ends that account's live sessions.
"""

from flask import Blueprint, current_app, request
from flask_login import current_user, login_required

from app.extensions import db
from app.models.user import User, UserRole
from app.responses import error_response, success_response
from app.security.account_rules import (
    is_valid_email,
    is_valid_name,
    normalize_email,
    password_problem,
)
from app.security.permissions import roles_required
from app.services.session_service import revoke_user_sessions

admin_staff_bp = Blueprint("admin_staff", __name__, url_prefix="/api/admin/staff")

STAFF_ROLES = (UserRole.ADMIN, UserRole.KITCHEN)
UPDATABLE_FIELDS = frozenset({"name", "role", "is_active", "password"})


def _json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _serialize(user):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _staff_query():
    return User.query.filter(User.role.in_(STAFF_ROLES))


def _invalid_role_response():
    return error_response("INVALID_ROLE", "Role must be ADMIN or KITCHEN.", 400)


def _audit(action, target, actor, **details):
    current_app.logger.info(
        "staff %s: target=%s actor=%s %s",
        action, target.id, actor.id,
        " ".join(f"{key}={value}" for key, value in sorted(details.items())),
    )


@admin_staff_bp.get("")
@login_required
@roles_required(UserRole.ADMIN)
def list_staff():
    users = _staff_query().order_by(User.name, User.id).all()
    return success_response("Staff retrieved", {"staff": [_serialize(user) for user in users]})


@admin_staff_bp.post("")
@login_required
@roles_required(UserRole.ADMIN)
def create_staff():
    payload = _json_object()
    if payload is None:
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    name = payload.get("name")
    email = payload.get("email")
    password = payload.get("password")
    role = payload.get("role")

    if not all(isinstance(value, str) for value in (name, email, password, role)):
        return error_response("INVALID_STAFF", "Name, email, role and password are required.", 400)

    name = " ".join(name.split())
    email = normalize_email(email)

    if not is_valid_name(name):
        return error_response("INVALID_STAFF", "Enter a name (up to 100 characters).", 400)
    if not is_valid_email(email):
        return error_response("INVALID_STAFF", "Enter a valid email address.", 400)
    if role not in STAFF_ROLES:
        return _invalid_role_response()

    problem = password_problem(password)
    if problem:
        return error_response("INVALID_STAFF", problem, 400)

    if User.query.filter_by(email=email).first() is not None:
        return error_response("EMAIL_UNAVAILABLE", "An account with this email already exists.", 409)

    user = User(name=name, email=email, role=role, is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    _audit("created", user, current_user, role=role)
    return success_response("Staff account created", _serialize(user), status=201)


@admin_staff_bp.patch("/<int:user_id>")
@login_required
@roles_required(UserRole.ADMIN)
def update_staff(user_id):
    user = _staff_query().filter(User.id == user_id).with_for_update().first()
    if user is None:
        return error_response("STAFF_NOT_FOUND", "Staff account not found.", 404)

    payload = _json_object()
    if payload is None:
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    unknown = sorted(set(payload) - UPDATABLE_FIELDS)
    if unknown:
        return error_response("INVALID_STAFF", f"Unsupported fields: {', '.join(unknown)}.", 400)
    if not payload:
        return error_response("INVALID_STAFF", "Provide a field to update.", 400)

    new_name = user.name
    if "name" in payload:
        if not isinstance(payload["name"], str) or not is_valid_name(" ".join(payload["name"].split())):
            return error_response("INVALID_STAFF", "Enter a name (up to 100 characters).", 400)
        new_name = " ".join(payload["name"].split())

    new_role = user.role
    if "role" in payload:
        if payload["role"] not in STAFF_ROLES:
            return _invalid_role_response()
        new_role = payload["role"]

    new_active = user.is_active
    if "is_active" in payload:
        if not isinstance(payload["is_active"], bool):
            return error_response("INVALID_STAFF", "'is_active' must be true or false.", 400)
        new_active = payload["is_active"]

    if "password" in payload:
        if not isinstance(payload["password"], str):
            return error_response("INVALID_STAFF", "Password must be text.", 400)
        problem = password_problem(payload["password"])
        if problem:
            return error_response("INVALID_STAFF", problem, 400)

    # Stop an administrator from removing their own access. Everyone else can be changed,
    # because the acting administrator stays active.
    removes_own_admin_access = user.id == current_user.id and (
        new_role != UserRole.ADMIN or not new_active
    )
    if removes_own_admin_access:
        return error_response("SELF_LOCKOUT", "You cannot remove your own admin access.", 409)

    access_changed = new_role != user.role or new_active != user.is_active
    password_changed = "password" in payload

    user.name = new_name
    user.role = new_role
    user.is_active = new_active
    if password_changed:
        user.set_password(payload["password"])
    db.session.commit()

    if access_changed or password_changed:
        # Role, status or password changed: end every live session so the new rules apply now.
        revoke_user_sessions(user.id)

    _audit(
        "updated", user, current_user,
        role=new_role, active=new_active, password_changed=password_changed,
    )
    return success_response("Staff account updated", _serialize(user))
