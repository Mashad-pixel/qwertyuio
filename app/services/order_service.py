import hashlib
import secrets
from datetime import timedelta

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment, PaymentRecordStatus
from app.services.collection_service import expire_collection_tokens
from app.services.canteen_service import get_status
from app.services.errors import OrderError
from app.services.order_details import CustomerDetails, request_fingerprint
from app.services.inventory_service import release_reservations, reserve_stock, return_sold_stock
from app.services.pricing_service import normalize_requested_items, price_order
from app.services.time_utils import as_utc, utcnow
from app.services.firebase_service import sync_order_to_firebase

MAX_IDEMPOTENCY_KEY_LENGTH = 64
EXPIRY_NOTE = "Payment not completed in time"


def _generate_order_number():
    stamp = utcnow().strftime("%y%m%d")
    return f"TU{stamp}{secrets.token_hex(4).upper()}"


def _hash_token(raw_token):
    # Only the hash is stored. The raw token is returned to the student once.
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _validate_idempotency_key(key):
    if key is None:
        return None
    key = key.strip()
    if not key or len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise OrderError(
            "INVALID_IDEMPOTENCY_KEY",
            f"Idempotency-Key must be 1 to {MAX_IDEMPOTENCY_KEY_LENGTH} characters.",
        )
    return key


def _find_existing_order(student_id, key):
    return Order.query.filter_by(student_id=student_id, idempotency_key=key).first()


def _assert_same_request(existing, requested, fingerprint):
    """A reused key must carry the same request. Otherwise it would return the wrong order."""
    if existing.request_fingerprint is not None:
        same = existing.request_fingerprint == fingerprint
    else:
        # Orders made before fingerprints existed: compare the items only.
        stored = sorted((line.menu_item_id, line.quantity) for line in existing.items)
        same = stored == sorted(requested)
    if not same:
        raise OrderError(
            "IDEMPOTENCY_KEY_REUSED",
            "This Idempotency-Key was already used for a different order.",
            409,
        )


def _reuse_existing(existing, requested, fingerprint):
    """Check a reused key before returning its order. The request must match, and the order must still be live.

    A cancelled order can never be paid, so returning it would leave the student stuck on it.
    """
    _assert_same_request(existing, requested, fingerprint)
    if existing.order_status == OrderStatus.CANCELLED:
        raise OrderError(
            "ORDER_CANCELLED",
            "This order was cancelled. Place a new order.",
            409,
        )


def payment_window_closed(order, now=None):
    """True once an unpaid order has waited longer than ORDER_PAYMENT_EXPIRY_MINUTES."""
    now = now or utcnow()
    minutes = current_app.config["ORDER_PAYMENT_EXPIRY_MINUTES"]
    return as_utc(order.created_at) <= now - timedelta(minutes=minutes)


def expire_order(order, now=None):
    """Cancel one unpaid order and free its held stock. The caller must commit."""
    now = now or utcnow()
    previous_status = order.order_status

    order.order_status = OrderStatus.CANCELLED
    order.payment_status = PaymentStatus.FAILED
    release_reservations(order.id)

    db.session.add(OrderStatusHistory(
        order_id=order.id,
        previous_status=previous_status,
        new_status=OrderStatus.CANCELLED,
        changed_by=None,  # System change, not a staff member
        changed_at=now,
        notes=EXPIRY_NOTE,
    ))


def expire_unpaid_orders():
    """Cancel every unpaid order whose payment window has closed. Returns how many.

    Paid orders are never touched. Runs lazily before each new order, and from the
    `expire-orders` CLI command. The whole sweep is one transaction, so a failure
    changes nothing.
    """
    now = utcnow()
    candidates = (
        Order.query.filter(
            Order.order_status == OrderStatus.PENDING_PAYMENT,
            Order.payment_status == PaymentStatus.PENDING,
        )
        .with_for_update()
        .all()
    )

    try:
        expired = 0
        for order in candidates:
            if payment_window_closed(order, now):
                expire_order(order, now)
                expired += 1
        db.session.commit()
        return expired
    except Exception:
        db.session.rollback()
        raise


def _sweep_expired_orders_safely():
    """Free stock held by expired orders before a new order is priced.

    If the sweep fails, students can still order. Their order may just see less
    free stock until the next sweep. The failure is logged.
    """
    try:
        expire_unpaid_orders()
    except Exception:
        current_app.logger.exception("Could not expire unpaid orders before creating a new order.")


def create_order(student_id, raw_items, idempotency_key=None, customer=None):
    """Create a pending_payment order and reserve its stock in one transaction.

    Returns (order, raw_tracking_token). raw_tracking_token is None when an existing
    order is returned for a retried key, because the raw token was shown the first time.
    A reused key with a different request raises IDEMPOTENCY_KEY_REUSED (409).
    """
    key = _validate_idempotency_key(idempotency_key)
    customer = customer or CustomerDetails()

    requested = normalize_requested_items(raw_items)
    fingerprint = request_fingerprint(requested, customer)

    if key:
        existing = _find_existing_order(student_id, key)
        if existing:
            _reuse_existing(existing, requested, fingerprint)
            return existing, None

    canteen = get_status()
    if not canteen["is_accepting_orders"]:
        # Show the message the canteen staff wrote, if they wrote one.
        raise OrderError(
            "CANTEEN_CLOSED",
            canteen["message"] or "The canteen is not accepting new orders right now.",
            409,
        )

    _sweep_expired_orders_safely()

    priced = price_order(requested)
    raw_token = secrets.token_urlsafe(32)

    order = Order(
        order_number=_generate_order_number(),
        student_id=student_id,
        idempotency_key=key,
        subtotal_paise=priced.subtotal_paise,
        discount_paise=priced.discount_paise,
        tax_paise=priced.tax_paise,
        total_paise=priced.total_paise,
        payment_status=PaymentStatus.PENDING,
        order_status=OrderStatus.PENDING_PAYMENT,
        tracking_token_hash=_hash_token(raw_token),
        request_fingerprint=fingerprint,
        customer_name=customer.name,
        customer_phone=customer.phone,
        instructions=customer.instructions,
    )

    for line in priced.lines:
        order.items.append(
            OrderItem(
                menu_item_id=line.menu_item_id,
                item_name_snapshot=line.item_name,
                unit_price_snapshot_paise=line.unit_price_paise,
                quantity=line.quantity,
                line_total_paise=line.line_total_paise,
            )
        )

    try:
        db.session.add(order)
        db.session.flush()  # Assigns order.id, which the stock reservations need.
        reserve_stock(order.id, priced.lines)
        db.session.commit()
    except IntegrityError:
        # A parallel request with the same key may have won the race.
        db.session.rollback()
        if key:
            existing = _find_existing_order(student_id, key)
            if existing:
                _reuse_existing(existing, requested, fingerprint)
                return existing, None
        raise OrderError(
            "ORDER_CREATE_FAILED",
            "Could not create the order. Please try again.",
            500,
        )
    except Exception:
        # Also covers OrderError from reserve_stock. The order and any partial holds are rolled back.
        db.session.rollback()
        raise

    committed_order = db.session.get(Order, order.id)
    if committed_order is not None:
        sync_order_to_firebase(committed_order)
    return committed_order or order, raw_token


def cancel_order(order_id, staff_user_id, reason):
    """Admin cancels an order. Returns (order, refund_required).

    Unpaid orders free their held stock. Paid orders get their sold stock back, and
    their money is flagged REFUND_REQUIRED until an admin refunds it. In both cases
    the collection code stops working immediately.
    """
    try:
        order = Order.query.filter_by(id=order_id).with_for_update().first()
        if order is None:
            raise OrderError("ORDER_NOT_FOUND", "Order not found.", 404)

        if order.order_status == OrderStatus.COLLECTED:
            raise OrderError(
                "ORDER_ALREADY_COLLECTED",
                "This order has already been collected and cannot be cancelled.",
                409,
            )
        if order.order_status == OrderStatus.CANCELLED:
            raise OrderError("ALREADY_CANCELLED", "This order is already cancelled.", 409)

        now = utcnow()
        previous_status = order.order_status

        release_reservations(order.id)
        return_sold_stock(order.id)
        expire_collection_tokens(order.id, now)

        captured_payments = Payment.query.filter(
            Payment.order_id == order.id,
            Payment.status.in_([PaymentRecordStatus.PAID, PaymentRecordStatus.PARTIALLY_REFUNDED]),
        ).all()
        for payment in captured_payments:
            payment.status = PaymentRecordStatus.REFUND_REQUIRED
        refund_required = bool(captured_payments)

        # Paid and partly refunded orders keep their payment status. Only unpaid orders change.
        if order.payment_status == PaymentStatus.PENDING:
            order.payment_status = PaymentStatus.FAILED

        order.order_status = OrderStatus.CANCELLED
        db.session.add(OrderStatusHistory(
            order_id=order.id,
            previous_status=previous_status,
            new_status=OrderStatus.CANCELLED,
            changed_by=staff_user_id,
            changed_at=now,
            notes=reason,
        ))

        db.session.commit()
        committed_order = db.session.get(Order, order.id)
        if committed_order is not None:
            sync_order_to_firebase(committed_order)
        return committed_order or order, refund_required

    except Exception:
        db.session.rollback()
        raise
