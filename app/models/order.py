from datetime import datetime, timezone

from app.extensions import db


class OrderStatus:
    PENDING_PAYMENT = "pending_payment"
    RECEIVED = "received"
    PREPARING = "preparing"
    READY = "ready"
    COLLECTED = "collected"
    CANCELLED = "cancelled"


class PaymentStatus:
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


def utcnow():
    return datetime.now(timezone.utc)


class Order(db.Model):
    __tablename__ = "orders"

    __table_args__ = (
        db.UniqueConstraint(
            "student_id",
            "idempotency_key",
            name="uq_orders_student_idempotency",
        ),
        db.CheckConstraint("subtotal_paise >= 0", name="ck_orders_subtotal_non_negative"),
        db.CheckConstraint("discount_paise >= 0", name="ck_orders_discount_non_negative"),
        db.CheckConstraint("tax_paise >= 0", name="ck_orders_tax_non_negative"),
        db.CheckConstraint("total_paise >= 0", name="ck_orders_total_non_negative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False, index=True)

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # Client-supplied Idempotency-Key header. Unique per student.
    idempotency_key = db.Column(db.String(64), nullable=True)

    # Hash of the items and checkout details sent with the key. A reused key with a different
    # request is refused. Orders created before this column existed have NULL here.
    request_fingerprint = db.Column(db.String(64), nullable=True)

    # Checkout details the student typed. Stored as entered (name trimmed, phone normalised).
    customer_name = db.Column(db.String(100), nullable=True)
    customer_phone = db.Column(db.String(20), nullable=True)
    instructions = db.Column(db.String(500), nullable=True)

    subtotal_paise = db.Column(db.Integer, nullable=False, default=0)
    discount_paise = db.Column(db.Integer, nullable=False, default=0)
    tax_paise = db.Column(db.Integer, nullable=False, default=0)
    total_paise = db.Column(db.Integer, nullable=False, default=0)

    payment_status = db.Column(
        db.String(30),
        nullable=False,
        default=PaymentStatus.PENDING,
        index=True,
    )
    order_status = db.Column(
        db.String(30),
        nullable=False,
        default=OrderStatus.PENDING_PAYMENT,
        index=True,
    )

    # SHA-256 hash of the private tracking token. The raw token is never stored.
    tracking_token_hash = db.Column(db.String(64), unique=True, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    items = db.relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
