from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import false as sql_false
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class UserRole:
    ADMIN = "ADMIN"
    KITCHEN = "KITCHEN"
    STUDENT = "STUDENT"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=UserRole.STUDENT, index=True)

    # Overrides UserMixin.is_active. load_user() rejects inactive users.
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    # Two-factor authentication (TOTP). Administrators must enable it before they can use
    # admin features; see app/__init__.py. The secret is base32 and is only used by the server.
    mfa_enabled = db.Column(db.Boolean, nullable=False, default=False, server_default=sql_false())
    mfa_secret = db.Column(db.String(64), nullable=True)
    mfa_last_step = db.Column(db.BigInteger, nullable=True)
    mfa_failed_attempts = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    mfa_locked_until = db.Column(db.DateTime(timezone=True), nullable=True)

    @property
    def mfa_required(self):
        return self.role == UserRole.ADMIN

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password, method="scrypt")

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)
