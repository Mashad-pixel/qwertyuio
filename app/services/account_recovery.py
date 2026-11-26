"""Password recovery: one-time email codes, single-use reset tokens, backup codes, and support requests.

Every answer that could reveal whether an account exists is the same whether or not it does.
Codes and reset tokens are stored only as hashes. A code is never written to the logs.
"""

import hashlib
import hmac
import logging
import re
import secrets
from datetime import timedelta

from flask import current_app

from app.extensions import db
from app.models.recovery import AccountRecoveryRequest, PasswordRecoveryChallenge, RecoveryCode
from app.models.user import User
from app.security.account_rules import is_valid_email, normalize_email, password_problem
from app.services.otp_delivery import DeliveryError, send_recovery_code
from app.services.time_utils import as_utc, utcnow

logger = logging.getLogger(__name__)

BACKUP_CODE_COUNT = 8
# No 0/O or 1/I/L, so codes can be read aloud or copied from paper without confusion.
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_PHONE_PATTERN = re.compile(r"^(?:\+91)?[6-9]\d{9}$")
_SEPARATORS = re.compile(r"[\s-]")

GENERIC_INVALID_CODE = "That code is incorrect or has expired. Check it and try again."
GENERIC_INVALID_RESET = "This reset link has expired. Start the password reset again."
GENERIC_BACKUP_CODE = "That recovery code is not valid. Check it and try again."


class RecoveryError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


# ---- helpers -------------------------------------------------------------------------------

def _keyed_hash(scope, value):
    """HMAC with the app secret. Short codes need a key, or a leaked table could be brute forced offline."""
    key = current_app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(key, f"{scope}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def _plain_hash(value):
    # For tokens with 256 bits of randomness, a plain SHA-256 is enough.
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def classify_identifier(raw):
    """Return ('email', value), ('phone', value), or None."""
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    email = normalize_email(value)
    if is_valid_email(email):
        return "email", email
    compact = _SEPARATORS.sub("", value)
    if _PHONE_PATTERN.fullmatch(compact):
        return "phone", "+91" + compact[-10:]
    return None


def _user_for_email(email):
    user = User.query.filter_by(email=email).first()
    if user is None or not user.is_active:
        return None
    return user


def _email_identifier_or_error(raw):
    kind = classify_identifier(raw)
    if kind is None:
        raise RecoveryError("INVALID_IDENTIFIER", "Enter a valid email address or 10-digit mobile number.", 400)
    return kind


def _new_backup_code():
    groups = ["".join(secrets.choice(_CODE_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "-".join(groups)


def _normalize_backup_code(raw):
    return re.sub(r"[^A-Za-z0-9]", "", str(raw)).upper()


# ---- password recovery by email code -------------------------------------------------------

def request_code(raw_identifier):
    """Start or resend a recovery code. Silent when no code is sent, so the answer never differs."""
    kind, value = _email_identifier_or_error(raw_identifier)
    if kind != "email":
        raise RecoveryError(
            "PHONE_RECOVERY_UNAVAILABLE",
            "Recovery by mobile number isn't available yet. Use the email address on your account.",
            400,
        )

    user = _user_for_email(value)
    if user is None:
        return

    now = utcnow()
    cooldown = current_app.config["RECOVERY_RESEND_SECONDS"]
    latest = (
        PasswordRecoveryChallenge.query.filter_by(user_id=user.id)
        .order_by(PasswordRecoveryChallenge.created_at.desc())
        .first()
    )
    if latest is not None and now - as_utc(latest.last_sent_at) < timedelta(seconds=cooldown):
        return

    hour_ago = now - timedelta(hours=1)
    recent = PasswordRecoveryChallenge.query.filter(
        PasswordRecoveryChallenge.user_id == user.id,
        PasswordRecoveryChallenge.created_at >= hour_ago,
    ).count()
    if recent >= current_app.config["RECOVERY_MAX_CODES_PER_HOUR"]:
        return

    _issue_code(user, now)


def _issue_code(user, now):
    code = f"{secrets.randbelow(10**6):06d}"
    minutes = current_app.config["RECOVERY_CODE_MINUTES"]

    # A new code replaces every code still outstanding for this user.
    outstanding = PasswordRecoveryChallenge.query.filter(
        PasswordRecoveryChallenge.user_id == user.id,
        PasswordRecoveryChallenge.code_consumed_at.is_(None),
    ).all()
    for old in outstanding:
        old.code_consumed_at = now

    challenge = PasswordRecoveryChallenge(
        user_id=user.id,
        code_hash=_keyed_hash(f"code:{user.id}", code),
        attempts=0,
        created_at=now,
        last_sent_at=now,
        expires_at=now + timedelta(minutes=minutes),
    )
    db.session.add(challenge)
    db.session.commit()

    try:
        send_recovery_code(user.email, code)
    except DeliveryError as exc:
        # The student still sees the generic message. The operator sees this line, and no code.
        logger.error("Recovery code for user %s was not delivered: %s", user.id, exc)


def verify_code(raw_identifier, raw_code):
    """Check the emailed code. Returns a single-use reset token on success."""
    kind, value = _email_identifier_or_error(raw_identifier)
    code = str(raw_code or "").strip()
    if kind != "email" or not re.fullmatch(r"\d{6}", code):
        raise RecoveryError("INVALID_CODE", GENERIC_INVALID_CODE, 400)

    user = _user_for_email(value)
    if user is None:
        raise RecoveryError("INVALID_CODE", GENERIC_INVALID_CODE, 400)

    now = utcnow()
    challenge = (
        PasswordRecoveryChallenge.query.filter(
            PasswordRecoveryChallenge.user_id == user.id,
            PasswordRecoveryChallenge.code_consumed_at.is_(None),
            PasswordRecoveryChallenge.expires_at > now,
        )
        .order_by(PasswordRecoveryChallenge.created_at.desc())
        .first()
    )
    if challenge is None:
        raise RecoveryError("INVALID_CODE", GENERIC_INVALID_CODE, 400)

    max_attempts = current_app.config["RECOVERY_MAX_ATTEMPTS"]
    expected = _keyed_hash(f"code:{user.id}", code)
    if not hmac.compare_digest(challenge.code_hash, expected):
        challenge.attempts += 1
        if challenge.attempts >= max_attempts:
            challenge.code_consumed_at = now  # Too many wrong tries: this code is dead.
        db.session.commit()
        raise RecoveryError("INVALID_CODE", GENERIC_INVALID_CODE, 400)

    return _grant_reset(challenge, user, now)


def _grant_reset(challenge, user, now):
    token = secrets.token_urlsafe(32)
    challenge.code_consumed_at = challenge.code_consumed_at or now
    challenge.reset_token_hash = _plain_hash(token)
    challenge.reset_expires_at = now + timedelta(minutes=current_app.config["RECOVERY_RESET_MINUTES"])
    db.session.commit()
    return token


# ---- backup recovery codes -----------------------------------------------------------------

def create_backup_codes(user):
    """Replace this user's unused backup codes. The raw codes are returned once and never stored."""
    RecoveryCode.query.filter_by(user_id=user.id, used_at=None).delete()
    codes = []
    while len(codes) < BACKUP_CODE_COUNT:
        code = _new_backup_code()
        if code in codes:
            continue
        codes.append(code)
        db.session.add(
            RecoveryCode(
                user_id=user.id,
                code_hash=_keyed_hash(f"backup:{user.id}", _normalize_backup_code(code)),
                created_at=utcnow(),
            )
        )
    db.session.commit()
    return codes


def redeem_backup_code(raw_identifier, raw_code):
    """Use one backup code. Each code works once. Returns a single-use reset token."""
    kind, value = _email_identifier_or_error(raw_identifier)
    normalized = _normalize_backup_code(raw_code or "")
    if kind != "email" or len(normalized) != 12:
        raise RecoveryError("INVALID_BACKUP_CODE", GENERIC_BACKUP_CODE, 400)

    user = _user_for_email(value)
    if user is None:
        raise RecoveryError("INVALID_BACKUP_CODE", GENERIC_BACKUP_CODE, 400)

    row = RecoveryCode.query.filter_by(
        user_id=user.id,
        code_hash=_keyed_hash(f"backup:{user.id}", normalized),
        used_at=None,
    ).first()
    if row is None:
        raise RecoveryError("INVALID_BACKUP_CODE", GENERIC_BACKUP_CODE, 400)

    now = utcnow()
    row.used_at = now
    challenge = PasswordRecoveryChallenge(
        user_id=user.id,
        code_hash=_keyed_hash("backup-redemption", str(row.id)),
        attempts=0,
        created_at=now,
        last_sent_at=now,
        expires_at=now,
        code_consumed_at=now,
    )
    db.session.add(challenge)
    db.session.flush()
    return _grant_reset(challenge, user, now)


# ---- reset ---------------------------------------------------------------------------------

def reset_password(raw_token, password):
    problem = password_problem(password)
    if problem:
        raise RecoveryError("INVALID_PASSWORD", problem, 400)
    if not isinstance(raw_token, str) or not raw_token:
        raise RecoveryError("INVALID_RESET", GENERIC_INVALID_RESET, 400)

    now = utcnow()
    challenge = PasswordRecoveryChallenge.query.filter_by(reset_token_hash=_plain_hash(raw_token)).first()
    if (
        challenge is None
        or challenge.used_at is not None
        or challenge.reset_expires_at is None
        or as_utc(challenge.reset_expires_at) <= now
    ):
        raise RecoveryError("INVALID_RESET", GENERIC_INVALID_RESET, 400)

    user = db.session.get(User, challenge.user_id)
    if user is None or not user.is_active:
        raise RecoveryError("INVALID_RESET", GENERIC_INVALID_RESET, 400)
    if user.check_password(password):
        raise RecoveryError("PASSWORD_UNCHANGED", "Choose a password you haven’t used before.", 400)

    user.set_password(password)
    user.password_changed_at = now

    # Use the token once, and kill every other outstanding code, token and session for this account.
    for other in PasswordRecoveryChallenge.query.filter_by(user_id=user.id, used_at=None).all():
        other.used_at = now
        other.code_consumed_at = other.code_consumed_at or now
    db.session.commit()


# ---- support requests ----------------------------------------------------------------------

def _text(payload, field, *, required, max_length, min_length=0):
    value = payload.get(field)
    if value is None or value == "":
        if required:
            raise RecoveryError("INVALID_REQUEST", f"Please fill in {field}.", 400)
        return None
    if not isinstance(value, str):
        raise RecoveryError("INVALID_REQUEST", f"{field} must be text.", 400)
    value = value.strip()
    if len(value) < min_length or len(value) > max_length:
        raise RecoveryError("INVALID_REQUEST", f"{field} must be {min_length} to {max_length} characters.", 400)
    return value or None


def _new_ref():
    return "REC-" + secrets.token_hex(4).upper()


def submit_support_request(payload):
    name = _text(payload, "name", required=True, max_length=100, min_length=2)
    identifier = payload.get("identifier")
    kind = classify_identifier(identifier)
    if kind is None:
        raise RecoveryError("INVALID_REQUEST", "Enter the email address or mobile number on the account.", 400)
    contact_email = normalize_email(str(payload.get("contactEmail") or ""))
    if not is_valid_email(contact_email):
        raise RecoveryError("INVALID_REQUEST", "Enter a valid contact email address.", 400)
    reason = _text(payload, "reason", required=True, max_length=1000, min_length=10)
    created_estimate = _text(payload, "createdEst", required=False, max_length=100)
    last_login_estimate = _text(payload, "lastLoginEst", required=False, max_length=100)
    extra = _text(payload, "extra", required=False, max_length=1000)

    # The match is recorded for staff only. The submitter sees the same reply either way.
    matched = _user_for_email(kind[1]) if kind[0] == "email" else None

    request = AccountRecoveryRequest(
        ref=_new_ref(),
        user_id=matched.id if matched else None,
        name=name,
        identifier=kind[1],
        contact_email=contact_email,
        created_estimate=created_estimate,
        last_login_estimate=last_login_estimate,
        reason=reason,
        extra=extra,
        status="pending",
        created_at=utcnow(),
    )
    db.session.add(request)
    db.session.commit()
    return request.ref
