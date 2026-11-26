from datetime import datetime, timezone

from app.extensions import db
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.order_status_history import OrderStatusHistory
from app.services.collection_service import issue_collection_token
from app.services.errors import OrderError
from app.services.firebase_service import sync_order_to_firebase

KITCHEN_QUEUE_STATUSES = (
    OrderStatus.RECEIVED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
)

ALL_ORDER_STATUSES = {
    OrderStatus.PENDING_PAYMENT,
    OrderStatus.RECEIVED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.COLLECTED,
    OrderStatus.CANCELLED,
}

# Moves the kitchen can make. "ready -> collected" is not here on purpose:
# it happens only when the collection QR is verified (step 4).
KITCHEN_TRANSITIONS = {
    OrderStatus.RECEIVED: {OrderStatus.PREPARING},
    OrderStatus.PREPARING: {OrderStatus.READY},
}

DEFAULT_QUEUE_LIMIT = 100
MAX_QUEUE_LIMIT = 200


def utcnow():
    return datetime.now(timezone.utc)


def parse_queue_limit(raw):
    if raw is None:
        return DEFAULT_QUEUE_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise OrderError("INVALID_PAGINATION", "'limit' must be a whole number.")
    if value < 1 or value > MAX_QUEUE_LIMIT:
        raise OrderError(
            "INVALID_PAGINATION",
            f"'limit' must be between 1 and {MAX_QUEUE_LIMIT}.",
        )
    return value


def get_kitchen_queue(status_filter, limit):
    """Return {status: [orders]} for paid orders that still need kitchen work.

    Unpaid orders never appear here. Each group is oldest first.
    """
    if status_filter is None:
        statuses = KITCHEN_QUEUE_STATUSES
    elif status_filter in KITCHEN_QUEUE_STATUSES:
        statuses = (status_filter,)
    else:
        raise OrderError(
            "INVALID_FILTER",
            f"Status filter must be one of: {', '.join(KITCHEN_QUEUE_STATUSES)}.",
        )

    queue = {}
    for status in statuses:
        queue[status] = (
            Order.query.filter(
                Order.payment_status == PaymentStatus.PAID,
                Order.order_status == status,
            )
            .order_by(Order.created_at.asc(), Order.id.asc())
            .limit(limit)
            .all()
        )
    return queue


def change_order_status(order_id, new_status, staff_user_id):
    """Move a paid order one step forward in the kitchen. Returns the updated order."""
    if new_status not in ALL_ORDER_STATUSES:
        raise OrderError("INVALID_STATUS", f"Unknown status '{new_status}'.", 400)

    if new_status == OrderStatus.COLLECTED:
        raise OrderError(
            "USE_COLLECTION_FLOW",
            "Orders are marked collected when the collection QR is verified.",
            409,
        )

    if new_status == OrderStatus.CANCELLED:
        raise OrderError(
            "CANCELLATION_NOT_AVAILABLE",
            "Cancellation is not available from the kitchen screen.",
            409,
        )

    if new_status not in (OrderStatus.PREPARING, OrderStatus.READY):
        raise OrderError(
            "INVALID_TRANSITION",
            f"The kitchen cannot set an order to '{new_status}'.",
            409,
        )

    try:
        # Lock the row, so two staff members can't change the same order at once.
        order = Order.query.filter_by(id=order_id).with_for_update().first()
        if order is None:
            raise OrderError("ORDER_NOT_FOUND", "Order not found.", 404)

        if order.payment_status != PaymentStatus.PAID:
            raise OrderError(
                "ORDER_NOT_PAID",
                "Unpaid orders cannot be prepared.",
                409,
            )

        previous_status = order.order_status
        if new_status not in KITCHEN_TRANSITIONS.get(previous_status, set()):
            raise OrderError(
                "INVALID_TRANSITION",
                f"Cannot move an order from '{previous_status}' to '{new_status}'.",
                409,
            )

        # Update only if the status is still what we just read. If another request
        # changed it first, this matches zero rows and the update is refused.
        updated_rows = (
            Order.query.filter(
                Order.id == order_id,
                Order.order_status == previous_status,
                Order.payment_status == PaymentStatus.PAID,
            ).update(
                {"order_status": new_status, "updated_at": utcnow()},
                synchronize_session=False,
            )
        )
        if updated_rows != 1:
            raise OrderError(
                "STATUS_CHANGED",
                "This order was just updated by someone else. Refresh and try again.",
                409,
            )

        db.session.add(OrderStatusHistory(
            order_id=order_id,
            previous_status=previous_status,
            new_status=new_status,
            changed_by=staff_user_id,
            changed_at=utcnow(),
        ))

        if new_status == OrderStatus.READY:
            # The student's collection QR is created when the order becomes ready.
            issue_collection_token(order_id)

        db.session.commit()
        updated_order = db.session.get(Order, order_id)
        if updated_order is not None:
            sync_order_to_firebase(updated_order)
        return updated_order

    except Exception:
        db.session.rollback()
        raise
