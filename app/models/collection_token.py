from app.extensions import db
from app.models.order import utcnow


class CollectionToken(db.Model):
    __tablename__ = "collection_tokens"

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Random value stored with the token. The raw token is rebuilt from this and
    # SECRET_KEY, so it never needs to be stored in plain text.
    token_nonce = db.Column(db.String(64), nullable=False)

    # SHA-256 of the raw token. Used to find the row when staff scan a QR code.
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)

    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
