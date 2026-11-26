from app.extensions import db
from app.models.order import utcnow


class RefundStatus:
    PENDING = "pending"      # Razorpay accepted the refund, not yet processed
    PROCESSED = "processed"  # Money returned to the customer
    FAILED = "failed"        # Razorpay could not refund


class Refund(db.Model):
    __tablename__ = "refunds"

    __table_args__ = (
        db.CheckConstraint("amount_paise > 0", name="ck_refunds_amount_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)

    payment_id = db.Column(
        db.Integer,
        db.ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Razorpay refund ID (rfnd_...). Unique, so a refund is recorded only once.
    provider_refund_id = db.Column(db.String(64), unique=True, nullable=False)

    amount_paise = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=RefundStatus.PENDING, index=True)
    reason = db.Column(db.String(255), nullable=True)

    requested_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    processed_at = db.Column(db.DateTime(timezone=True), nullable=True)
