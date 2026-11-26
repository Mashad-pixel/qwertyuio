from flask import Blueprint, jsonify, request
from flask_login import login_required

from app.models.menu import MenuItem
from app.models.user import UserRole
from app.responses import error_response
from app.security.permissions import roles_required
from app.services.canteen_service import update_status
from app.services.errors import ServiceValidationError
from app.services.firebase_service import firebase_connection_status
from app.services.menu_service import (
    MenuValidationError,
    create_menu_item,
    serialize_menu_item,
    update_menu_item,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _validation_error(details):
    response, status = error_response("VALIDATION_FAILED", "Validation failed.", 400)
    payload = response.get_json()
    payload["details"] = details
    return jsonify(payload), status


@admin_bp.get("/menu")
@login_required
@roles_required(UserRole.ADMIN)
def list_menu_items():
    items = MenuItem.query.order_by(MenuItem.category, MenuItem.name, MenuItem.id).all()
    return jsonify(items=[serialize_menu_item(item) for item in items]), 200


@admin_bp.post("/menu")
@login_required
@roles_required(UserRole.ADMIN)
def create_item():
    data = _json_object()
    if data is None:
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)
    try:
        item = create_menu_item(data)
    except MenuValidationError as exc:
        return _validation_error(exc.errors)
    return jsonify(item=serialize_menu_item(item)), 201


@admin_bp.patch("/menu/<int:item_id>")
@login_required
@roles_required(UserRole.ADMIN)
def update_item(item_id):
    item = MenuItem.query.filter_by(id=item_id).with_for_update().first()
    if item is None:
        return error_response("MENU_ITEM_NOT_FOUND", "Menu item not found.", 404)
    data = _json_object()
    if data is None:
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)
    try:
        item = update_menu_item(item, data)
    except MenuValidationError as exc:
        return _validation_error(exc.errors)
    return jsonify(item=serialize_menu_item(item)), 200


@admin_bp.patch("/canteen/status")
@login_required
@roles_required(UserRole.ADMIN)
def update_canteen_status():
    data = _json_object()
    if data is None:
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)
    try:
        status = update_status(data)
    except ServiceValidationError as exc:
        return _validation_error(exc.errors)
    return jsonify(status), 200


@admin_bp.get("/firebase/status")
@login_required
@roles_required(UserRole.ADMIN)
def firebase_status():
    """Admin-only Firebase Admin SDK health status; never exposes credentials."""
    status = firebase_connection_status()
    http_status = 200 if status["connected"] or not status["enabled"] else 503
    return jsonify(success=status["connected"], firebase=status), http_status
