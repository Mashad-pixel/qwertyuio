from flask import Blueprint, request
from flask_login import current_user, login_required

from app.models.user import UserRole
from app.responses import error_response, success_response
from app.security.permissions import roles_required
from app.services.errors import OrderError
from app.services.order_query_service import (
    get_order_for_admin,
    get_status_history,
    get_students_for_orders,
    list_orders_for_admin,
    pagination_info,
    parse_pagination,
    validate_order_status,
    validate_payment_status,
)
from app.services.order_serializer import (
    serialize_order_for_admin,
    serialize_status_history,
)
from app.services.order_service import cancel_order

admin_orders_bp = Blueprint("admin_orders", __name__, url_prefix="/api/admin/orders")

MAX_CANCEL_REASON = 255


def _order_error(exc):
    return error_response(exc.code, exc.message, exc.status)


@admin_orders_bp.route("", methods=["GET"])
@login_required
@roles_required(UserRole.ADMIN)
def list_all_orders():
    try:
        page, per_page = parse_pagination(request.args)
        order_status = validate_order_status(request.args.get("order_status"))
        payment_status = validate_payment_status(request.args.get("payment_status"))
    except OrderError as exc:
        return _order_error(exc)

    pagination = list_orders_for_admin(
        page,
        per_page,
        order_status=order_status,
        payment_status=payment_status,
    )
    students = get_students_for_orders(pagination.items)

    return success_response("Orders retrieved", {
        "orders": [
            serialize_order_for_admin(order, students.get(order.student_id))
            for order in pagination.items
        ],
        "pagination": pagination_info(pagination),
    })


@admin_orders_bp.route("/<int:order_id>", methods=["GET"])
@login_required
@roles_required(UserRole.ADMIN)
def get_any_order(order_id):
    order = get_order_for_admin(order_id)
    if order is None:
        return error_response("ORDER_NOT_FOUND", "Order not found.", 404)

    students = get_students_for_orders([order])
    data = serialize_order_for_admin(order, students.get(order.student_id))
    data["status_history"] = serialize_status_history(get_status_history(order.id))

    return success_response("Order retrieved", data)


@admin_orders_bp.route("/<int:order_id>/cancel", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN)
def cancel_order_route(order_id):
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    reason = payload.get("reason", "Cancelled by admin")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > MAX_CANCEL_REASON:
        return error_response(
            "INVALID_REASON",
            f"'reason' must be text of 1 to {MAX_CANCEL_REASON} characters.",
            400,
        )

    try:
        order, refund_required = cancel_order(order_id, current_user.id, reason.strip())
    except OrderError as exc:
        return _order_error(exc)

    students = get_students_for_orders([order])
    data = serialize_order_for_admin(order, students.get(order.student_id))
    # True when money was captured and must be refunded through /api/admin/payments/<id>/refund.
    data["refund_required"] = refund_required
    return success_response("Order cancelled", data)
