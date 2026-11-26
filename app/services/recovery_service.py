"""Password recovery: email codes, single-use reset tokens, backup codes and support requests.

Rules that hold everywhere in this module:
- Responses never reveal whether an account exists. Wrong, expired and unknown inputs get the same answer.
- Codes and tokens are stored only as keyed hashes. A copy of the database cannot be used to reset a password.
- A reset token works once and expires. Setting a password ends every session the account has.
"""

import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from flask import current_app

from app.extensions import db
from app.models.recovery import OtpChallenge, PasswordResetToken, RecoveryCode, RecoveryRequest
from app.models.user import User
from app.security.account_rules import is_valid_email, is_valid_name, normalize_email, password_problem
from app.services.mail_service import send_mail
from app.services.session_service import revoke_user_sessions
from app.services.time_utils import as_utc, utcnow

OTP_TTL = timedelta(minutes=5)
OTP_MAX_ATTEMPTS = 5
RESET_TTL = timedelta(minutes=10)
RECOVERY_CODE_COUNT = 10
# Base32 without 0, 1, I and O, so codes are easy to read and copy.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
RECOVERY_CODE_LENGTH = 12
REFERENCE_LENGTH = 8

GENERIC_CODE_MESSAGE = "That code isn't right, or it has expired. Check it or request a new code."
GENERIC_RESET_MESSAGE = "This reset link has expired or was already used. Start again from the sign-in page."
GENERIC_RECOVERY_MESSAGE = "That recovery code isn't valid for this account."

_MOBILE_PATTERN = re.compile(r"[+()\d\s-]+")


class RecoveryError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _keyed_hash(purpose, value):
    key = current_app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(key, f"{purpose}\x1f{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def _sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _random_code(length):
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def classify_identifier(raw):
    """Return ("email", address), ("mobile", number) or None for text a person typed."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    email = normalize_email(text)
    if is_valid_email(email):
        return ("email", email)
    if _MOBILE_PATTERN.fullmatch(text):
        digits = re.sub(r"\D", "", text)
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if re.fullmatch(r"[6-9]\d{9}", digits):
            return ("mobile", digits)
    return None


def _active_user_by_email(email):
    user = User.query.filter_by(email=email).first()
    if user is None or not user.is_active:
        return None
    return user


def _equalize_timing():
    """Do the same kind of work for unknown accounts, so response times don't reveal them."""
    _keyed_hash("otp", "0:000000")


def _retire_open_challenges(user_id, now):
    OtpChallenge.query.filter(
        OtpChallenge.user_id == user_id,
        OtpChallenge.consumed_at.is_(None),
    ).update({"consumed_at": now}, synchronize_session=False)


def start_email_recovery(email):
    """Email a new code if the address belongs to an active account. Always returns None."""
    user = _active_user_by_email(email)
    if user is None:
        _equalize_timing()
        return None

    now = utcnow()
    _retire_open_challenges(user.id, now)
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.session.add(OtpChallenge(
        user_id=user.id,
        purpose="reset",
        code_hash=_keyed_hash("otp", f"{user.id}:{code}"),
        attempts=0,
        expires_at=now + OTP_TTL,
        created_at=now,
    ))
    db.session.commit()

    send_mail(
        user.email,
        "Your TrayUP password reset code",
        f"Your TrayUP code is {code}. It expires in 5 minutes.\n\n"
        "If you did not ask to reset your password, you can ignore this email.",
    )
    return None


def _issue_reset_token(user, now):
    raw = secrets.token_urlsafe(32)
    db.session.add(PasswordResetToken(
        token_hash=_sha256(raw),
        user_id=user.id,
        expires_at=now + RESET_TTL,
        created_at=now,
    ))
    return raw


def verify_email_code(email, code):
    """Check an emailed code. Returns a single-use reset token."""
    user = _active_user_by_email(email)
    now = utcnow()
    if user is None or not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
        _equalize_timing()
        raise RecoveryError("CODE_INVALID", GENERIC_CODE_MESSAGE)

    challenge = (
        OtpChallenge.query
        .filter(
            OtpChallenge.user_id == user.id,
            OtpChallenge.consumed_at.is_(None),
            OtpChallenge.expires_at > now,
        )
        .order_by(OtpChallenge.created_at.desc())
        .first()
    )
    if challenge is None or challenge.attempts >= OTP_MAX_ATTEMPTS:
        if challenge is not None:
            challenge.consumed_at = now
            db.session.commit()
        raise RecoveryError("CODE_INVALID", GENERIC_CODE_MESSAGE)

    challenge.attempts += 1
    expected = _keyed_hash("otp", f"{user.id}:{code}")
    if not hmac.compare_digest(challenge.code_hash, expected):
        db.session.commit()
        raise RecoveryError("CODE_INVALID", GENERIC_CODE_MESSAGE)

    challenge.consumed_at = now
    raw = _issue_reset_token(user, now)
    db.session.commit()
    return raw


def consume_recovery_code(email, code):
    """Check a backup code. Each code works once. Returns a single-use reset token."""
    user = _active_user_by_email(email)
    normalized = re.sub(r"[\s-]", "", code).upper() if isinstance(code, str) else ""
    if user is None or not re.fullmatch(rf"[{CODE_ALPHABET}]{{{RECOVERY_CODE_LENGTH}}}", normalized):
        _equalize_timing()
        raise RecoveryError("RECOVERY_CODE_INVALID", GENERIC_RECOVERY_MESSAGE)

    target = _keyed_hash("recovery", normalized)
    match = None
    # Compare every stored code, so the time taken does not show which one matched.
    for row in RecoveryCode.query.filter(RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None)):
        if hmac.compare_digest(row.code_hash, target):
            match = row
    if match is None:
        raise RecoveryError("RECOVERY_CODE_INVALID", GENERIC_RECOVERY_MESSAGE)

    now = utcnow()
    match.used_at = now
    raw = _issue_reset_token(user, now)
    db.session.commit()
    return raw


def generate_recovery_codes(user):
    """Create a new set of backup codes and retire the previous set. Returns the plain codes once."""
    now = utcnow()
    RecoveryCode.query.filter(
        RecoveryCode.user_id == user.id,
        RecoveryCode.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)

    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = _random_code(RECOVERY_CODE_LENGTH)
        codes.append(f"{raw[:4]}-{raw[4:8]}-{raw[8:]}")
        db.session.add(RecoveryCode(user_id=user.id, code_hash=_keyed_hash("recovery", raw), created_at=now))
    db.session.commit()
    return codes


def reset_password(raw_token, new_password):
    """Set a new password with a valid reset token, then sign the account out everywhere."""
    if not isinstance(raw_token, str) or not raw_token:
        raise RecoveryError("RESET_INVALID", GENERIC_RESET_MESSAGE)
    now = utcnow()
    row = db.session.get(PasswordResetToken, _sha256(raw_token))
    if row is None or row.used_at is not None or as_utc(row.expires_at) <= now:
        raise RecoveryError("RESET_INVALID", GENERIC_RESET_MESSAGE)

    user = db.session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise RecoveryError("RESET_INVALID", GENERIC_RESET_MESSAGE)

    # Checked before the token is used, so a weak password can be corrected without starting again.
    problem = password_problem(new_password) if isinstance(new_password, str) else "Enter a password."
    if problem:
        raise RecoveryError("PASSWORD_INVALID", problem)

    user.set_password(new_password)
    row.used_at = now
    PasswordResetToken.query.filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)
    _retire_open_challenges(user.id, now)
    db.session.commit()

    revoke_user_sessions(user.id)
    current_app.logger.info("password reset completed for user %s", user.id)
    return user


def verify_current_password(user, password):
    return isinstance(password, str) and user.check_password(password)


_SUPPORT_LIMITS = {
    "name": 80,
    "identifier": 120,
    "contactEmail": 120,
    "createdEst": 60,
    "lastLoginEst": 60,
    "reason": 1000,
    "extra": 1000,
}


def submit_recovery_request(data):
    """Store a support request for manual review. Returns its reference."""
    errors = {}

    name = data.get("name")
    name = " ".join(name.split()) if isinstance(name, str) else ""
    if not is_valid_name(name) or len(name) < 2:
        errors["name"] = "Enter your full name."

    identifier = classify_identifier(data.get("identifier"))
    if identifier is None:
        errors["identifier"] = "Enter the email address or mobile number on the account."

    contact = data.get("contactEmail")
    contact = normalize_email(contact) if isinstance(contact, str) else ""
    if not is_valid_email(contact):
        errors["contactEmail"] = "Enter a valid contact email address."

    reason = data.get("reason")
    reason = reason.strip() if isinstance(reason, str) else ""
    if len(reason) < 10:
        errors["reason"] = "Tell us briefly what happened (at least 10 characters)."

    cleaned = {}
    for field, limit in _SUPPORT_LIMITS.items():
        value = data.get(field, "")
        if value is None:
            value = ""
        if not isinstance(value, str):
            errors[field] = "Must be text."
        elif len(value) > limit:
            errors[field] = f"Must be at most {limit} characters."
        else:
            cleaned[field] = value.strip()

    if errors:
        raise RecoveryError("VALIDATION_FAILED", "Please check the highlighted fields.", 400)

    reference = "TRY-" + _random_code(REFERENCE_LENGTH)
    db.session.add(RecoveryRequest(
        reference=reference,
        name=name,
        identifier=identifier[1],
        contact_email=contact,
        created_estimate=cleaned["createdEst"],
        last_login_estimate=cleaned["lastLoginEst"],
        reason=reason,
        extra=cleaned["extra"],
        status="received",
        created_at=utcnow(),
    ))
    db.session.commit()
    current_app.logger.info("recovery request %s received", reference)
    return reference


def list_recovery_requests(limit=100):
    rows = RecoveryRequest.query.order_by(RecoveryRequest.created_at.desc()).limit(limit).all()
    return [
        {
            "reference": row.reference,
            "name": row.name,
            "identifier": row.identifier,
            "contact_email": row.contact_email,
            "created_estimate": row.created_estimate,
            "last_login_estimate": row.last_login_estimate,
            "reason": row.reason,
            "extra": row.extra,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
