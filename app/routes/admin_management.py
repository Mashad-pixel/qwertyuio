"""Admin-only management endpoints: menu categories, canteen details and staff accounts.

Every route requires an administrator. Kitchen staff cannot reach any of these.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.models.menu_category import MenuCategory
from app.models.user import UserRole
from app.responses import error_response
from app.security.permissions import roles_required
from app.services.canteen_service import get_settings, update_details
from app.services.category_service import (
    create_category,
    delete_category,
    list_categories,
    serialize_category,
    update_category,
)
from app.services.errors import OrderError, ServiceValidationError
from app.services.staff_service import (
    create_staff,
    get_staff,
    list_staff,
    serialize_staff,
    update_staff,
)
from app.extensions import db

admin_management_bp = Blueprint("admin_management", __name__, url_prefix="/api/admin")


def _json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _validation_error(details):
    response, status = error_response("VALIDATION_FAILED", "Validation failed.", 400)
    payload = response.get_json()
    payload["details"] = details
    return jsonify(payload), status


def _order_error(exc):
    return error_response(exc.code, exc.message, exc.status)


def _invalid_json():
    return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)


# ---------- Menu categories ----------

@admin_management_bp.get("/categories")
@login_required
@roles_required(UserRole.ADMIN)
def categories_index():
    return jsonify(categories=list_categories()), 200


@admin_management_bp.post("/categories")
@login_required
@roles_required(UserRole.ADMIN)
def categories_create():
    data = _json_object()
    if data is None:
        return _invalid_json()
    try:
        category = create_category(data)
    except ServiceValidationError as exc:
        return _validation_error(exc.errors)
    except OrderError as exc:
        return _order_error(exc)
    return jsonify(category=serialize_category(category, 0)), 201


@admin_management_bp.patch("/categories/<int:category_id>")
@login_required
@roles_required(UserRole.ADMIN)
def categories_update(category_id):
    category = db.session.get(MenuCategory, category_id)
    if category is None:
        return error_response("CATEGORY_NOT_FOUND", "Category not found.", 404)
    data = _json_object()
    if data is None:
        return _invalid_json()
    try:
        category = update_category(category, data)
    except ServiceValidationError as exc:
        return _validation_error(exc.errors)
    except OrderError as exc:
        return _order_error(exc)
    row = next(row for row in list_categories() if row["id"] == category.id)
    return jsonify(category=row), 200


@admin_management_bp.delete("/categories/<int:category_id>")
@login_required
@roles_required(UserRole.ADMIN)
def categories_delete(category_id):
    category = db.session.get(MenuCategory, category_id)
    if category is None:
        return error_response("CATEGORY_NOT_FOUND", "Category not found.", 404)
    try:
        delete_category(category)
    except OrderError as exc:
        return _order_error(exc)
    return jsonify(success=True, message="Category deleted"), 200


# ---------- Canteen details ----------

@admin_management_bp.get("/canteen/settings")
@login_required
@roles_required(UserRole.ADMIN)
def canteen_settings_show():
    return jsonify(get_settings()), 200


@admin_management_bp.patch("/canteen/settings")
@login_required
@roles_required(UserRole.ADMIN)
def canteen_settings_update():
    data = _json_object()
    if data is None:
        return _invalid_json()
    try:
        settings = update_details(data)
    except ServiceValidationError as exc:
        return _validation_error(exc.errors)
    return jsonify(settings), 200


# ---------- Staff accounts ----------

@admin_management_bp.get("/staff")
@login_required
@roles_required(UserRole.ADMIN)
def staff_index():
    return jsonify(staff=[serialize_staff(user) for user in list_staff()]), 200


@admin_management_bp.post("/staff")
@login_required
@roles_required(UserRole.ADMIN)
def staff_create():
    data = _json_object()
    if data is None:
        return _invalid_json()
    try:
        user = create_staff(data, current_user)
    except ServiceValidationError as exc:
        return _validation_error(exc.errors)
    except OrderError as exc:
        return _order_error(exc)
    return jsonify(staff=serialize_staff(user)), 201


@admin_management_bp.patch("/staff/<int:user_id>")
@login_required
@roles_required(UserRole.ADMIN)
def staff_update(user_id):
    try:
        user = get_staff(user_id)
    except OrderError as exc:
        return _order_error(exc)
    data = _json_object()
    if data is None:
        return _invalid_json()
    try:
        user = update_staff(user, data, current_user)
    except ServiceValidationError as exc:
        return _validation_error(exc.errors)
    except OrderError as exc:
        return _order_error(exc)
    return jsonify(staff=serialize_staff(user)), 200
