from flask import Blueprint, request
from flask_login import current_user, login_required

from app.extensions import limiter
from app.models.user import UserRole
from app.security.permissions import roles_required
from app.responses import error_response, success_response
from app.services.collection_service import as_utc, get_student_collection_qr
from app.services.errors import OrderError
from app.services.order_details import parse_customer_details
from app.services.order_query_service import (
    get_order_for_student,
    list_orders_for_student,
    pagination_info,
    parse_pagination,
)
from app.services.order_serializer import serialize_order, serialize_tracking
from app.services.order_service import create_order

orders_bp = Blueprint("orders", __name__, url_prefix="/api/orders")


def _order_error(exc):
    return error_response(exc.code, exc.message, exc.status)


@orders_bp.route("", methods=["POST"])
@login_required
@roles_required(UserRole.STUDENT)
@limiter.limit("10 per minute")
def create_order_route():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    try:
        customer = parse_customer_details(payload)
        order, raw_token = create_order(
            student_id=current_user.id,
            raw_items=payload.get("items"),
            idempotency_key=request.headers.get("Idempotency-Key"),
            customer=customer,
        )
    except OrderError as exc:
        return _order_error(exc)

    if raw_token is not None:
        return success_response(
            "Order created successfully",
            serialize_order(order, raw_token),
            201,
        )

    # Retry with the same Idempotency-Key: return the original order.
    return success_response("Existing order returned", serialize_order(order), 200)


@orders_bp.route("", methods=["GET"])
@login_required
@roles_required(UserRole.STUDENT)
def list_my_orders():
    try:
        page, per_page = parse_pagination(request.args)
    except OrderError as exc:
        return _order_error(exc)

    pagination = list_orders_for_student(current_user.id, page, per_page)

    return success_response("Orders retrieved", {
        "orders": [serialize_order(order) for order in pagination.items],
        "pagination": pagination_info(pagination),
    })


@orders_bp.route("/<int:order_id>", methods=["GET"])
@login_required
@roles_required(UserRole.STUDENT)
def get_my_order(order_id):
    order = get_order_for_student(current_user.id, order_id)
    if order is None:
        # Same response whether the order doesn't exist or belongs to someone else.
        return error_response("ORDER_NOT_FOUND", "Order not found.", 404)

    return success_response("Order retrieved", serialize_order(order))


@orders_bp.route("/<int:order_id>/tracking", methods=["GET"])
@login_required
@roles_required(UserRole.STUDENT)
def get_my_order_tracking(order_id):
    order = get_order_for_student(current_user.id, order_id)
    if order is None:
        return error_response("ORDER_NOT_FOUND", "Order not found.", 404)

    return success_response("Order status retrieved", serialize_tracking(order))


@orders_bp.route("/<int:order_id>/collection-qr", methods=["GET"])
@login_required
@roles_required(UserRole.STUDENT)
def get_collection_qr(order_id):
    try:
        raw_token, token, order = get_student_collection_qr(order_id, current_user.id)
    except OrderError as exc:
        return _order_error(exc)

    response, status = success_response("Collection code retrieved", {
        "token": raw_token,
        "expires_at": as_utc(token.expires_at).isoformat(),
        "order_number": order.order_number,
    })
    # Keep the collection code out of browser and proxy caches.
    response.headers["Cache-Control"] = "no-store"
    return response, status
