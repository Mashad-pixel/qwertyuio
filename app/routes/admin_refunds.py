from flask import Blueprint, request
from flask_login import current_user, login_required

from app.models.payment import Payment
from app.models.refund import Refund
from app.models.user import UserRole
from app.responses import error_response, success_response
from app.security.permissions import roles_required
from app.services.errors import OrderError
from app.services.refund_service import list_payment_summaries, list_recent_refunds, request_refund

admin_refunds_bp = Blueprint("admin_refunds", __name__, url_prefix="/api/admin/payments")

MAX_REFUND_REASON = 255


def _order_error(exc):
    return error_response(exc.code, exc.message, exc.status)


def serialize_refund(refund):
    return {
        "id": refund.id,
        "payment_id": refund.payment_id,
        "order_id": refund.order_id,
        "provider_refund_id": refund.provider_refund_id,
        "amount_paise": refund.amount_paise,
        "status": refund.status,
        "reason": refund.reason,
        "requested_by": refund.requested_by,
        "created_at": refund.created_at.isoformat(),
        "processed_at": refund.processed_at.isoformat() if refund.processed_at else None,
    }


@admin_refunds_bp.route("/<int:payment_id>/refund", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN)
def create_refund(payment_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    amount = payload.get("amount_paise")
    if amount is not None and (isinstance(amount, bool) or not isinstance(amount, int) or amount < 1):
        return error_response(
            "INVALID_AMOUNT",
            "'amount_paise' must be a whole number of at least 1.",
            400,
        )

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > MAX_REFUND_REASON:
        return error_response(
            "INVALID_REASON",
            f"'reason' is required and must be 1 to {MAX_REFUND_REASON} characters.",
            400,
        )

    try:
        refund, payment, order = request_refund(
            payment_id,
            current_user.id,
            amount,
            reason.strip(),
        )
    except OrderError as exc:
        return _order_error(exc)

    data = serialize_refund(refund)
    data["payment_status"] = payment.status
    data["order_payment_status"] = order.payment_status
    return success_response("Refund requested", data, 201)


@admin_refunds_bp.route("/<int:payment_id>/refunds", methods=["GET"])
@login_required
@roles_required(UserRole.ADMIN)
def list_refunds(payment_id):
    if Payment.query.filter_by(id=payment_id).first() is None:
        return error_response("PAYMENT_NOT_FOUND", "Payment not found.", 404)

    refunds = Refund.query.filter_by(payment_id=payment_id).order_by(Refund.created_at.asc()).all()
    return success_response("Refunds retrieved", [serialize_refund(item) for item in refunds])


@admin_refunds_bp.route("", methods=["GET"])
@login_required
@roles_required(UserRole.ADMIN)
def list_payments():
    """Payments with refund totals and what can still be refunded. Newest first."""
    limit = _limit_arg(default=50, maximum=200)
    if limit is None:
        return error_response("INVALID_PAGINATION", "'limit' must be between 1 and 200.", 400)
    return success_response("Payments retrieved", {"payments": list_payment_summaries(limit)})


@admin_refunds_bp.route("/refunds", methods=["GET"])
@login_required
@roles_required(UserRole.ADMIN)
def list_all_refunds():
    """Recent refunds across all orders, newest first."""
    limit = _limit_arg(default=50, maximum=200)
    if limit is None:
        return error_response("INVALID_PAGINATION", "'limit' must be between 1 and 200.", 400)
    return success_response("Refunds retrieved", {"refunds": list_recent_refunds(limit)})


def _limit_arg(default, maximum):
    raw = request.args.get("limit", str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if 1 <= value <= maximum else None
