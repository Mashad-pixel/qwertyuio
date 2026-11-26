from app.extensions import db
from app.models.order import utcnow


class PresenceToken(db.Model):
    """One rotating QR code shown on an authorized canteen screen.

    Only a keyed digest of the raw token is stored. The raw value exists only in the QR
    code. Many students may redeem the same token, but each student only once.
    """

    __tablename__ = "presence_tokens"

    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    issued_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    issued_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)


class PresenceRedemption(db.Model):
    """A student's successful QR + GPS check against one token.

    Holds only audit facts. Latitude, longitude and timestamps of the GPS reading are never
    stored.
    """

    __tablename__ = "presence_redemptions"

    __table_args__ = (
        db.UniqueConstraint("token_id", "student_id", name="uq_presence_redemptions_token_student"),
        db.CheckConstraint("distance_meters >= 0", name="ck_presence_redemptions_distance_non_negative"),
        db.CheckConstraint("accuracy_meters >= 0", name="ck_presence_redemptions_accuracy_non_negative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    token_id = db.Column(
        db.Integer,
        db.ForeignKey("presence_tokens.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    redeemed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    distance_meters = db.Column(db.Integer, nullable=False)
    accuracy_meters = db.Column(db.Integer, nullable=False)


class PresenceSession(db.Model):
    """A short-lived, student-specific permission to place exactly one order.

    The raw session token is returned to the student once. Only its keyed digest is stored.
    """

    __tablename__ = "presence_sessions"

    __table_args__ = (
        db.UniqueConstraint("redemption_id", name="uq_presence_sessions_redemption"),
        # An order can be tied to at most one verification session.
        db.UniqueConstraint("order_id", name="uq_presence_sessions_order"),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    redemption_id = db.Column(
        db.Integer,
        db.ForeignKey("presence_redemptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    consumed_at = db.Column(db.DateTime(timezone=True), nullable=True)
