from app.extensions import db
from app.models.order import utcnow


class OrderStatusHistory(db.Model):
    __tablename__ = "order_status_history"

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    previous_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=False)

    # NULL means the system made the change, for example when a payment is confirmed.
    changed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    changed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    notes = db.Column(db.String(255), nullable=True)
