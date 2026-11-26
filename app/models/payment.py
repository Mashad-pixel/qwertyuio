from app.extensions import db
from app.models.order import utcnow


class PaymentRecordStatus:
    CREATED = "created"                        # Razorpay order exists, waiting for payment
    PAID = "paid"                              # Payment captured and confirmed for the order
    REFUND_REQUIRED = "refund_required"        # Money captured, but the order can't be fulfilled
    PARTIALLY_REFUNDED = "partially_refunded"  # Some of the money has been returned
    REFUNDED = "refunded"                      # All of the money has been returned


class Payment(db.Model):
    __tablename__ = "payments"

    __table_args__ = (
        db.CheckConstraint("amount_paise > 0", name="ck_payments_amount_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    payment_provider = db.Column(db.String(20), nullable=False, default="razorpay")

    # Razorpay order ID (order_...). Unique, so one Razorpay order maps to one row.
    provider_order_id = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # Razorpay payment ID (pay_...). Set once a payment is captured.
    provider_payment_id = db.Column(db.String(64), unique=True, nullable=True)

    amount_paise = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")

    status = db.Column(
        db.String(20),
        nullable=False,
        default=PaymentRecordStatus.CREATED,
        index=True,
    )

    verified_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
