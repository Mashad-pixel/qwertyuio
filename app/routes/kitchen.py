from flask import Blueprint, request
from flask_login import current_user, login_required

from app.extensions import limiter
from app.models.user import UserRole
from app.responses import error_response, success_response
from app.security.permissions import roles_required
from app.services.collection_service import confirm_collection, preview_collection
from app.services.errors import OrderError
from app.services.kitchen_service import (
    change_order_status,
    get_kitchen_queue,
    parse_queue_limit,
)
from app.services.order_serializer import serialize_order

kitchen_bp = Blueprint("kitchen", __name__, url_prefix="/api/kitchen")

KITCHEN_ACCESS = (UserRole.KITCHEN, UserRole.ADMIN)


def _order_error(exc):
    return error_response(exc.code, exc.message, exc.status)


def _read_collection_token():
    """Return (token, None) or (None, error_response)."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    token = payload.get("token")
    if not isinstance(token, str) or not token.strip():
        return None, error_response("MISSING_TOKEN", "A 'token' value is required.", 400)

    return token.strip(), None


@kitchen_bp.route("/orders", methods=["GET"])
@login_required
@roles_required(*KITCHEN_ACCESS)
def kitchen_queue():
    try:
        limit = parse_queue_limit(request.args.get("limit"))
        queue = get_kitchen_queue(request.args.get("status"), limit)
    except OrderError as exc:
        return _order_error(exc)

    return success_response("Kitchen queue retrieved", {
        "queue": {
            status: [serialize_order(order) for order in orders]
            for status, orders in queue.items()
        },
        "limit": limit,
    })


@kitchen_bp.route("/orders/<int:order_id>/status", methods=["PATCH"])
@login_required
@roles_required(*KITCHEN_ACCESS)
def update_order_status(order_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    status = payload.get("status")
    if not isinstance(status, str) or not status.strip():
        return error_response("INVALID_STATUS", "A 'status' value is required.", 400)

    try:
        order = change_order_status(order_id, status.strip().lower(), current_user.id)
    except OrderError as exc:
        return _order_error(exc)

    return success_response("Order status updated", serialize_order(order))


@kitchen_bp.route("/collection/verify", methods=["POST"])
@login_required
@roles_required(*KITCHEN_ACCESS)
@limiter.limit("30 per minute")
def verify_collection_code():
    """Show the order behind a scanned code. Does not change anything."""
    token, error = _read_collection_token()
    if error is not None:
        return error

    try:
        order = preview_collection(token)
    except OrderError as exc:
        return _order_error(exc)

    return success_response("Collection code is valid", serialize_order(order))


@kitchen_bp.route("/collection/confirm", methods=["POST"])
@login_required
@roles_required(*KITCHEN_ACCESS)
@limiter.limit("30 per minute")
def confirm_collection_code():
    """Staff confirm the handover. The order becomes collected and the code can't be used again."""
    token, error = _read_collection_token()
    if error is not None:
        return error

    try:
        order = confirm_collection(token, current_user.id)
    except OrderError as exc:
        return _order_error(exc)

    return success_response("Order collected", serialize_order(order))
