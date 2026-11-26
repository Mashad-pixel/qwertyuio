from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.order_status_history import OrderStatusHistory
from app.models.user import User
from app.services.errors import OrderError

DEFAULT_PER_PAGE = 10
MAX_PER_PAGE = 50

VALID_ORDER_STATUSES = {
    OrderStatus.PENDING_PAYMENT,
    OrderStatus.RECEIVED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.COLLECTED,
    OrderStatus.CANCELLED,
}

VALID_PAYMENT_STATUSES = {
    PaymentStatus.PENDING,
    PaymentStatus.PAID,
    PaymentStatus.FAILED,
    PaymentStatus.REFUNDED,
    PaymentStatus.PARTIALLY_REFUNDED,
}


def _parse_positive_int(raw, default, name):
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise OrderError("INVALID_PAGINATION", f"'{name}' must be a whole number.")
    if value < 1:
        raise OrderError("INVALID_PAGINATION", f"'{name}' must be at least 1.")
    return value


def parse_pagination(args):
    """Return (page, per_page) from query-string arguments."""
    page = _parse_positive_int(args.get("page"), 1, "page")
    per_page = _parse_positive_int(args.get("per_page"), DEFAULT_PER_PAGE, "per_page")

    if per_page > MAX_PER_PAGE:
        raise OrderError(
            "INVALID_PAGINATION",
            f"'per_page' cannot be more than {MAX_PER_PAGE}.",
        )
    return page, per_page


def validate_order_status(value):
    if value is None:
        return None
    if value not in VALID_ORDER_STATUSES:
        raise OrderError("INVALID_FILTER", f"Unknown order_status '{value}'.")
    return value


def validate_payment_status(value):
    if value is None:
        return None
    if value not in VALID_PAYMENT_STATUSES:
        raise OrderError("INVALID_FILTER", f"Unknown payment_status '{value}'.")
    return value


def pagination_info(pagination):
    return {
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }


def _newest_first(query):
    return query.order_by(Order.created_at.desc(), Order.id.desc())


def list_orders_for_student(student_id, page, per_page):
    query = Order.query.filter_by(student_id=student_id)
    return _newest_first(query).paginate(page=page, per_page=per_page, error_out=False)


def get_order_for_student(student_id, order_id):
    # Filtering by student_id here prevents students from reading other students' orders (IDOR).
    return Order.query.filter_by(id=order_id, student_id=student_id).first()


def list_orders_for_admin(page, per_page, order_status=None, payment_status=None):
    query = Order.query
    if order_status is not None:
        query = query.filter(Order.order_status == order_status)
    if payment_status is not None:
        query = query.filter(Order.payment_status == payment_status)
    return _newest_first(query).paginate(page=page, per_page=per_page, error_out=False)


def get_order_for_admin(order_id):
    return Order.query.filter_by(id=order_id).first()


def get_students_for_orders(orders):
    """Load all students for a page of orders in one query. Returns {user_id: User}."""
    student_ids = {order.student_id for order in orders}
    if not student_ids:
        return {}
    users = User.query.filter(User.id.in_(student_ids)).all()
    return {user.id: user for user in users}


def get_status_history(order_id):
    return (
        OrderStatusHistory.query.filter_by(order_id=order_id)
        .order_by(OrderStatusHistory.changed_at.asc(), OrderStatusHistory.id.asc())
        .all()
    )
