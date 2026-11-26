from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, limiter
from app.models.user import User, UserRole
from app.security import totp
from app.security.account_rules import is_valid_email, is_valid_name, normalize_email, password_problem
from app.services import mfa_service
from app.services.mfa_service import MfaError
from app.services.session_service import (
    mark_current_session_mfa_verified,
    revoke_current_session,
    start_session,
)
from app.services.time_utils import as_utc, utcnow

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Checked when the email doesn't exist, so response time doesn't reveal which emails are registered.
_DUMMY_HASH = generate_password_hash("not-a-real-password")

# Holds the user id between a correct password and a correct authenticator code. The
# password step does not log the user in, so nothing privileged is reachable yet.
_PENDING_MFA_KEY = "mfa_pending"


def success_response(message, data=None, status=200):
    return jsonify({"success": True, "message": message, "data": data or {}}), status


def error_response(code, message, status):
    return (
        jsonify({"success": False, "message": message, "error": {"code": code}}),
        status,
    )


def invalid_credentials_response():
    # Same message whether the email is unknown, the password is wrong, or the account is disabled.
    return error_response("INVALID_CREDENTIALS", "Invalid email or password.", 401)


def serialize_user(user):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
    }


def _current_db_user():
    return db.session.get(User, current_user.id)


def _pending_mfa_user():
    """Return the user who passed the password step and is still within the code window."""
    pending = session.get(_PENDING_MFA_KEY)
    if not isinstance(pending, dict):
        return None
    try:
        user_id = int(pending["uid"])
        since = as_utc(datetime.fromisoformat(pending["since"]))
    except (KeyError, TypeError, ValueError):
        session.pop(_PENDING_MFA_KEY, None)
        return None

    window = timedelta(minutes=current_app.config["MFA_PENDING_MINUTES"])
    if utcnow() - since > window:
        session.pop(_PENDING_MFA_KEY, None)
        return None

    user = db.session.get(User, user_id)
    if user is None or not user.is_active or not user.mfa_enabled:
        session.pop(_PENDING_MFA_KEY, None)
        return None
    return user


def _finish_login(user, mfa_verified):
    """Create the real session for a user who has completed every required step."""
    session.clear()
    login_user(user)
    start_session(user, mfa_verified=mfa_verified)


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    email = payload.get("email")
    password = payload.get("password")

    if not isinstance(email, str) or not isinstance(password, str):
        return error_response("MISSING_FIELDS", "Email and password are required.", 400)

    email = email.strip().lower()
    if not email or not password:
        return error_response("MISSING_FIELDS", "Email and password are required.", 400)

    user = User.query.filter_by(email=email).first()

    if user is None:
        check_password_hash(_DUMMY_HASH, password)
        return invalid_credentials_response()

    if not user.check_password(password) or not user.is_active:
        return invalid_credentials_response()

    if user.mfa_enabled:
        # Password is right, but nothing is logged in until the authenticator code is too.
        session.clear()
        session[_PENDING_MFA_KEY] = {"uid": user.id, "since": utcnow().isoformat()}
        return success_response(
            "Enter the code from your authenticator app.",
            {"mfa_required": True, "csrf_token": generate_csrf()},
        )

    # Administrators without a second factor get a session that cannot use admin features
    # until they enroll one. The login response tells the page to show enrollment.
    _finish_login(user, mfa_verified=not user.mfa_required)

    data = serialize_user(user)
    data["csrf_token"] = generate_csrf()
    if user.mfa_required:
        data["mfa_setup_required"] = True
        return success_response("Set up two-factor authentication to continue.", data)
    return success_response("Logged in successfully", data)


@auth_bp.route("/mfa/verify", methods=["POST"])
@limiter.limit("10 per minute")
def mfa_verify():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    user = _pending_mfa_user()
    if user is None:
        return error_response("MFA_SESSION_EXPIRED", "Sign in again to continue.", 401)

    code = payload.get("code")
    if not isinstance(code, str):
        return error_response("MISSING_FIELDS", "Enter the 6-digit code.", 400)

    try:
        accepted = mfa_service.verify_login_code(user, code.strip().replace(" ", ""))
    except MfaError as exc:
        return error_response(exc.code, exc.message, exc.status)

    if not accepted:
        return error_response("INVALID_MFA_CODE", "That code is not correct. Try again.", 400)

    _finish_login(user, mfa_verified=True)
    data = serialize_user(user)
    data["csrf_token"] = generate_csrf()
    return success_response("Logged in successfully", data)


@auth_bp.route("/mfa/setup", methods=["POST"])
@login_required
def mfa_setup():
    try:
        secret = mfa_service.begin_enrollment(_current_db_user())
    except MfaError as exc:
        return error_response(exc.code, exc.message, exc.status)
    return success_response(
        "Add this key to your authenticator app, then confirm with a code.",
        {
            "secret": secret,
            "otpauth_uri": totp.provisioning_uri(secret, current_user.email),
        },
    )


@auth_bp.route("/mfa/confirm", methods=["POST"])
@login_required
def mfa_confirm():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    code = payload.get("code")
    if not isinstance(code, str):
        return error_response("MISSING_FIELDS", "Enter the 6-digit code.", 400)

    try:
        mfa_service.confirm_enrollment(_current_db_user(), code.strip().replace(" ", ""))
    except MfaError as exc:
        return error_response(exc.code, exc.message, exc.status)

    mark_current_session_mfa_verified()
    return success_response(
        "Two-factor authentication is on.",
        {"mfa_enabled": True, "csrf_token": generate_csrf()},
    )


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    revoke_current_session()
    logout_user()
    session.clear()
    return success_response("Logged out successfully", {"csrf_token": generate_csrf()})


@auth_bp.route("/me", methods=["GET"])
@login_required
def me():
    return success_response("Current user", serialize_user(current_user))


def email_unavailable_response():
    return error_response(
        "EMAIL_UNAVAILABLE",
        "An account with this email already exists. Try logging in instead.",
        409,
    )


@auth_bp.route("/register", methods=["POST"])
@limiter.limit(lambda: current_app.config.get("REGISTER_RATE_LIMIT", "20 per hour; 100 per day"))
def register():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    name = payload.get("name")
    email = payload.get("email")
    password = payload.get("password")

    # The browser cannot choose a privileged role.
    if not isinstance(name, str) or not isinstance(email, str) or not isinstance(password, str):
        return error_response("INVALID_REGISTRATION", "Name, email and password are required.", 400)

    name = name.strip()
    email = normalize_email(email)

    if not is_valid_name(name):
        return error_response("INVALID_REGISTRATION", "Enter your name (up to 100 characters).", 400)
    if not is_valid_email(email):
        return error_response("INVALID_REGISTRATION", "Enter a valid email address.", 400)

    problem = password_problem(password)
    if problem:
        return error_response("INVALID_REGISTRATION", problem, 400)

    if User.query.filter_by(email=email).first() is not None:
        return email_unavailable_response()

    user = User(name=name, email=email, role=UserRole.STUDENT, is_active=True)
    user.set_password(password)
    db.session.add(user)

    try:
        db.session.commit()
    except IntegrityError:
        # The unique email constraint handles concurrent duplicate registrations.
        db.session.rollback()
        return email_unavailable_response()

    _finish_login(user, mfa_verified=not user.mfa_required)
    data = serialize_user(user)
    data["csrf_token"] = generate_csrf()
    return success_response("Account created", data, status=201)
