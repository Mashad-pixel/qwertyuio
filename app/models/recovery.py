from app.extensions import db
from app.services.time_utils import utcnow


class OtpChallenge(db.Model):
    """A 6-digit email code for a password reset. Only a keyed hash of the code is stored."""

    __tablename__ = "otp_challenges"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    purpose = db.Column(db.String(20), nullable=False)
    code_hash = db.Column(db.String(64), nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    consumed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class PasswordResetToken(db.Model):
    """A single-use token that allows one password change. Only its SHA-256 hash is stored."""

    __tablename__ = "password_reset_tokens"

    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class RecoveryCode(db.Model):
    """A one-time backup code. Only a keyed hash is stored, and the plain code is shown once."""

    __tablename__ = "recovery_codes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    code_hash = db.Column(db.String(64), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class RecoveryRequest(db.Model):
    """A support request from someone who cannot reach their email or recovery codes.

    Nothing changes on an account from this record. An administrator verifies ownership first.
    """

    __tablename__ = "recovery_requests"

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(20), nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    identifier = db.Column(db.String(120), nullable=False)
    contact_email = db.Column(db.String(120), nullable=False)
    created_estimate = db.Column(db.String(60), nullable=False, default="")
    last_login_estimate = db.Column(db.String(60), nullable=False, default="")
    reason = db.Column(db.String(1000), nullable=False)
    extra = db.Column(db.String(1000), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="received")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
