from app.extensions import db
from app.models.order import utcnow


class AttemptStatus:
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SUCCESS = SUCCEEDED
    SIGNATURE_FAILED = "signature_failed"
    REFUND_REQUIRED = "refund_required"


class PaymentAttempt(db.Model):
    __tablename__ = "payment_attempts"

    __table_args__ = (
        db.UniqueConstraint("order_id", "attempt_number", name="uq_payment_attempts_order_number"),
        # Prevents duplicate audit rows when the same Razorpay event is seen twice.
        db.UniqueConstraint(
            "provider_payment_id",
            "status",
            name="uq_payment_attempts_payment_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider_order_id = db.Column(db.String(64), nullable=False, index=True)
    provider_payment_id = db.Column(db.String(64), nullable=True, index=True)

    attempt_number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    failure_reason = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
