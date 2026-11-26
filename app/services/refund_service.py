from datetime import timezone


from app.extensions import db
from app.models.order import Order, PaymentStatus
from app.models.payment import Payment, PaymentRecordStatus
from app.models.refund import Refund, RefundStatus
from app.services.errors import OrderError
from app.services.razorpay_client import PROVIDER_ERRORS, get_razorpay_client
from app.services.time_utils import utcnow


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _sync_payment_status(payment):
    refunds = Refund.query.filter_by(payment_id=payment.id).all()
    processed = sum(r.amount_paise for r in refunds if r.status == RefundStatus.PROCESSED)
    pending = sum(r.amount_paise for r in refunds if r.status == RefundStatus.PENDING)
    remaining = payment.amount_paise - processed

    if processed and remaining <= 0:
        payment.status = PaymentRecordStatus.REFUNDED
        order_status = PaymentStatus.REFUNDED
    elif processed:
        payment.status = PaymentRecordStatus.PARTIALLY_REFUNDED
        order_status = PaymentStatus.PARTIALLY_REFUNDED
    elif pending:
        payment.status = PaymentRecordStatus.REFUND_REQUIRED
        order_status = PaymentStatus.PAID
    else:
        payment.status = PaymentRecordStatus.PAID
        order_status = PaymentStatus.PAID

    order = db.session.get(Order, payment.order_id)
    if order:
        order.payment_status = order_status


def request_refund(payment_id, admin_id, amount_paise, reason):
    """Request a full or partial refund. Status changes after Razorpay confirmation."""
    try:
        payment = Payment.query.filter_by(id=payment_id).with_for_update().first()
        if payment is None:
            raise OrderError("PAYMENT_NOT_FOUND", "Payment not found.", 404)

        order = db.session.get(Order, payment.order_id)
        if order is None:
            raise OrderError("ORDER_NOT_FOUND", "Order not found.", 404)

        if payment.status not in [PaymentRecordStatus.PAID, PaymentRecordStatus.REFUND_REQUIRED, PaymentRecordStatus.PARTIALLY_REFUNDED]:
            raise OrderError("PAYMENT_NOT_REFUNDABLE", "This payment cannot be refunded.", 409)

        amount = payment.amount_paise if amount_paise is None else amount_paise
        already = sum(
            r.amount_paise
            for r in Refund.query.filter_by(payment_id=payment.id).all()
            if r.status in [RefundStatus.PENDING, RefundStatus.PROCESSED]
        )
        if amount > payment.amount_paise - already:
            raise OrderError("REFUND_TOO_LARGE", "Refund exceeds the remaining captured amount.", 400)

        client = get_razorpay_client()
        try:
            result = client.payment.refund(
                payment.provider_payment_id,
                {"amount": amount, "notes": {"reason": reason}},
            )
        except PROVIDER_ERRORS as exc:
            raise OrderError("REFUND_PROVIDER_ERROR", "Razorpay could not accept the refund. Please retry.", 502) from exc

        now = utcnow()
        status = RefundStatus.PROCESSED if result.get("status") == "processed" else RefundStatus.PENDING
        refund = Refund(
            payment_id=payment.id,
            order_id=order.id,
            provider_refund_id=result["id"],
            amount_paise=amount,
            status=status,
            reason=reason,
            requested_by=admin_id,
            created_at=now,
            processed_at=now if status == RefundStatus.PROCESSED else None,
        )
        db.session.add(refund)
        db.session.flush()
        _sync_payment_status(payment)
        db.session.commit()
        return refund, payment, order

    except Exception:
        db.session.rollback()
        raise


def _refund_by_provider_id(provider_refund_id):
    return Refund.query.filter_by(provider_refund_id=provider_refund_id).with_for_update().first()


def _update_refund(refund, status):
    if refund.status == status:
        return
    if refund.status == RefundStatus.PROCESSED:
        return  # Never reverse a confirmed refund if an older failure event arrives later.
    refund.status = status
    refund.processed_at = utcnow() if status == RefundStatus.PROCESSED else None

    payment = db.session.get(Payment, refund.payment_id)
    if payment:
        _sync_payment_status(payment)


def handle_refund_processed_event(entity):
    provider_refund_id = entity.get("id")
    if not provider_refund_id:
        return "ignored"  # Malformed event. Retrying would not help.
    refund = _refund_by_provider_id(provider_refund_id)
    if refund is None:
        # The webhook may beat our request transaction. Raising asks Razorpay to retry later.
        raise OrderError("REFUND_NOT_FOUND", "Refund record is not available yet. Retry webhook.", 404)
    _update_refund(refund, RefundStatus.PROCESSED)
    return "processed"


def handle_refund_failed_event(entity):
    provider_refund_id = entity.get("id")
    if not provider_refund_id:
        return "ignored"
    refund = _refund_by_provider_id(provider_refund_id)
    if refund is None:
        raise OrderError("REFUND_NOT_FOUND", "Refund record is not available yet. Retry webhook.", 404)
    _update_refund(refund, RefundStatus.FAILED)
    return "processed"


def reconcile_refund_status(payment_id):
    """Read-only summary useful for an admin's reconciliation screen."""
    payment = Payment.query.filter_by(id=payment_id).first()
    if payment is None:
        raise OrderError("PAYMENT_NOT_FOUND", "Payment not found.", 404)
    refunds = Refund.query.filter_by(payment_id=payment_id).all()
    return {
        "payment_id": payment.id,
        "payment_status": payment.status,
        "captured_paise": payment.amount_paise,
        "refunded_paise": sum(r.amount_paise for r in refunds if r.status == RefundStatus.PROCESSED),
        "pending_refund_paise": sum(r.amount_paise for r in refunds if r.status == RefundStatus.PENDING),
        "remaining_paise": payment.amount_paise - sum(
            r.amount_paise for r in refunds if r.status == RefundStatus.PROCESSED
        ),
    }


REFUNDABLE_RECORD_STATUSES = (
    PaymentRecordStatus.PAID,
    PaymentRecordStatus.REFUND_REQUIRED,
    PaymentRecordStatus.PARTIALLY_REFUNDED,
)


def list_payment_summaries(limit=50):
    """Recent payments with their refund totals and what can still be refunded (admin view).

    Refund totals are summed in one grouped query, so the list does not query once per payment.
    """
    from sqlalchemy import func

    payments = Payment.query.order_by(Payment.created_at.desc(), Payment.id.desc()).limit(limit).all()
    if not payments:
        return []

    payment_ids = [payment.id for payment in payments]
    totals = {}
    for payment_id, status, total in (
        db.session.query(Refund.payment_id, Refund.status, func.sum(Refund.amount_paise))
        .filter(Refund.payment_id.in_(payment_ids))
        .group_by(Refund.payment_id, Refund.status)
        .all()
    ):
        totals.setdefault(payment_id, {})[status] = int(total or 0)

    orders = {order.id: order for order in Order.query.filter(Order.id.in_({p.order_id for p in payments})).all()}

    summaries = []
    for payment in payments:
        order = orders.get(payment.order_id)
        paid_back = totals.get(payment.id, {}).get(RefundStatus.PROCESSED, 0)
        waiting = totals.get(payment.id, {}).get(RefundStatus.PENDING, 0)
        refundable = (
            max(0, payment.amount_paise - paid_back - waiting)
            if payment.status in REFUNDABLE_RECORD_STATUSES else 0
        )
        summaries.append({
            "payment_id": payment.id,
            "order_id": payment.order_id,
            "order_number": order.order_number if order else None,
            "order_status": order.order_status if order else None,
            "payment_status": payment.status,
            "currency": payment.currency,
            "amount_paise": payment.amount_paise,
            "refunded_paise": paid_back,
            "pending_refund_paise": waiting,
            "refundable_paise": refundable,
            "created_at": payment.created_at.isoformat() if payment.created_at else None,
        })
    return summaries


def list_recent_refunds(limit=50):
    rows = (
        db.session.query(Refund, Order.order_number)
        .join(Order, Order.id == Refund.order_id)
        .order_by(Refund.created_at.desc(), Refund.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": refund.id,
            "payment_id": refund.payment_id,
            "order_number": order_number,
            "amount_paise": refund.amount_paise,
            "status": refund.status,
            "reason": refund.reason,
            "requested_by": refund.requested_by,
            "created_at": refund.created_at.isoformat() if refund.created_at else None,
            "processed_at": refund.processed_at.isoformat() if refund.processed_at else None,
        }
        for refund, order_number in rows
    ]
