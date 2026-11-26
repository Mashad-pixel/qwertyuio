from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class UserSession(db.Model):
    """A server-side login session.

    The browser holds a random token. Only its SHA-256 hash is stored, so a copy of the
    database cannot be used to log in. Revoking a row ends the session immediately, even
    if the browser still holds the cookie.
    """

    __tablename__ = "user_sessions"

    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    mfa_verified = db.Column(db.Boolean, nullable=False, default=False)
