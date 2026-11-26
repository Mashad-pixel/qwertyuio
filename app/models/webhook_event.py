from app.extensions import db
from app.models.order import utcnow


class WebhookStatus:
    RECEIVED = "received"    # Stored, not yet processed (or processing failed mid-way)
    PROCESSED = "processed"  # Applied to orders or payments
    IGNORED = "ignored"      # Valid event we don't act on (or refers to an unknown payment)
    FAILED = "failed"        # Processing raised an error. Razorpay will retry delivery.


class WebhookEvent(db.Model):
    __tablename__ = "webhook_events"

    id = db.Column(db.Integer, primary_key=True)

    # X-Razorpay-Event-Id header. Unique, so duplicate deliveries are detected.
    provider_event_id = db.Column(db.String(100), unique=True, nullable=False, index=True)

    event_type = db.Column(db.String(60), nullable=False)

    # SHA-256 of the raw request body, for audit. The body itself is not stored.
    payload_hash = db.Column(db.String(64), nullable=False)

    processing_status = db.Column(
        db.String(20),
        nullable=False,
        default=WebhookStatus.RECEIVED,
        index=True,
    )
    last_error = db.Column(db.String(500), nullable=True)

    received_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    processed_at = db.Column(db.DateTime(timezone=True), nullable=True)
