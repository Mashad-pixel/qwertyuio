"""Two-factor (TOTP) enrollment and verification.

Failed codes are counted on the user row, not in the browser session. A client that drops
its cookie therefore cannot reset the count, and the lockout applies to the account.
"""

from datetime import timedelta

from flask import current_app

from app.extensions import db
from app.security import totp
from app.services.time_utils import as_utc, utcnow


class MfaError(Exception):
    def __init__(self, code, message, status):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def is_locked(user):
    return user.mfa_locked_until is not None and as_utc(user.mfa_locked_until) > utcnow()


def _ensure_not_locked(user):
    if is_locked(user):
        raise MfaError("MFA_LOCKED", "Too many incorrect codes. Try again later.", 429)


def _record_failure(user):
    limit = current_app.config["MFA_MAX_FAILED_ATTEMPTS"]
    user.mfa_failed_attempts = (user.mfa_failed_attempts or 0) + 1
    if user.mfa_failed_attempts >= limit:
        user.mfa_locked_until = utcnow() + timedelta(minutes=current_app.config["MFA_LOCKOUT_MINUTES"])
        user.mfa_failed_attempts = 0
    db.session.commit()


def _reset_failures(user):
    user.mfa_failed_attempts = 0
    user.mfa_locked_until = None


def begin_enrollment(user):
    """Create a new secret for the user. Nothing is enforced until the first code is confirmed."""
    if user.mfa_enabled:
        raise MfaError("MFA_ALREADY_ENABLED", "Two-factor authentication is already set up.", 409)
    user.mfa_secret = totp.generate_secret()
    user.mfa_last_step = None
    _reset_failures(user)
    db.session.commit()
    return user.mfa_secret


def confirm_enrollment(user, code):
    """Turn MFA on, after the user proves their app holds the new secret."""
    if user.mfa_enabled:
        raise MfaError("MFA_ALREADY_ENABLED", "Two-factor authentication is already set up.", 409)
    if not user.mfa_secret:
        raise MfaError("MFA_NOT_STARTED", "Start two-factor setup first.", 400)
    _ensure_not_locked(user)

    step = totp.verify_code(user.mfa_secret, code)
    if step is None:
        _record_failure(user)
        raise MfaError("INVALID_MFA_CODE", "That code is not correct. Check your authenticator app and try again.", 400)

    user.mfa_enabled = True
    user.mfa_last_step = step
    _reset_failures(user)
    db.session.commit()


def verify_login_code(user, code):
    """Return True if the code completes a login. Wrong codes count toward the lockout."""
    if not user.mfa_enabled or not user.mfa_secret:
        return False
    _ensure_not_locked(user)

    step = totp.verify_code(user.mfa_secret, code, last_used_step=user.mfa_last_step)
    if step is None:
        _record_failure(user)
        return False

    user.mfa_last_step = step
    _reset_failures(user)
    db.session.commit()
    return True
