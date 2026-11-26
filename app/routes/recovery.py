"""Password recovery endpoints used by the student sign-in page.

Anyone can call the recovery endpoints, so each one is rate limited. Requests are keyed by the
identifier they name, so one person cannot keep trying an account from many addresses.
"""

import hashlib

from flask import Blueprint, current_app, request
from flask_login import current_user, login_required

from app.extensions import limiter
from app.models.user import UserRole
from app.responses import error_response, success_response
from app.security.permissions import roles_required
from app.services import recovery_service
from app.services.mail_service import MailError, mail_configured
from app.services.recovery_service import RecoveryError, classify_identifier

recovery_bp = Blueprint("recovery", __name__, url_prefix="/api")

START_MESSAGE = (
    "If an account matches that email address, a 6-digit code has been sent. "
    "It expires in 5 minutes."
)


def _json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _identifier_key():
    payload = request.get_json(silent=True)
    raw = payload.get("identifier") if isinstance(payload, dict) else None
    value = raw.strip().lower() if isinstance(raw, str) else ""
    return "recovery-identifier:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:40]


def _invalid_json():
    return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)


def _start_recovery():
    payload = _json_object()
    if payload is None:
        return _invalid_json()

    identifier = classify_identifier(payload.get("identifier"))
    if identifier is None:
        return error_response("INVALID_IDENTIFIER", "Enter a valid email address.", 400)
    if identifier[0] == "mobile":
        # Mobile numbers are not stored on accounts, so codes can only go by email for now.
        return error_response(
            "MOBILE_RESET_UNAVAILABLE",
            "Password reset by mobile number isn't available yet. Use the email address on your account.",
            400,
        )
    if not mail_configured():
        current_app.logger.error("password reset requested but email is not configured")
        return error_response(
            "MAIL_NOT_CONFIGURED",
            "Email is not set up on this server, so codes cannot be sent. Contact support.",
            503,
        )

    try:
        recovery_service.start_email_recovery(identifier[1])
    except MailError:
        # Same answer as success, so a delivery problem does not reveal which accounts exist.
        current_app.logger.error("password reset email could not be sent")
    return success_response(START_MESSAGE)


# Starting and resending are one endpoint served at two URLs, so both share one set of limits.
# Separate endpoints would count separately, and a resend could skip the cooldown.
@recovery_bp.post("/forgot/start")
@recovery_bp.post("/forgot/resend")
@limiter.limit("1 per 30 seconds", key_func=_identifier_key)
@limiter.limit("5 per 15 minutes", key_func=_identifier_key)
@limiter.limit("20 per hour")
def forgot_start():
    return _start_recovery()


@recovery_bp.post("/forgot/verify")
@limiter.limit("10 per 15 minutes", key_func=_identifier_key)
def forgot_verify():
    payload = _json_object()
    if payload is None:
        return _invalid_json()

    identifier = classify_identifier(payload.get("identifier"))
    if identifier is None or identifier[0] != "email":
        return error_response("CODE_INVALID", recovery_service.GENERIC_CODE_MESSAGE, 400)
    try:
        token = recovery_service.verify_email_code(identifier[1], payload.get("otp"))
    except RecoveryError as exc:
        return error_response(exc.code, exc.message, exc.status)
    return success_response("Code accepted.", {"resetToken": token})


@recovery_bp.post("/forgot/reset")
@limiter.limit("20 per 15 minutes")
def forgot_reset():
    payload = _json_object()
    if payload is None:
        return _invalid_json()
    try:
        recovery_service.reset_password(payload.get("resetToken"), payload.get("password"))
    except RecoveryError as exc:
        return error_response(exc.code, exc.message, exc.status)
    return success_response("Password updated. You have been signed out everywhere.")


@recovery_bp.post("/recovery/code")
@limiter.limit("10 per 15 minutes", key_func=_identifier_key)
def recovery_code():
    payload = _json_object()
    if payload is None:
        return _invalid_json()

    identifier = classify_identifier(payload.get("identifier"))
    if identifier is None or identifier[0] != "email":
        return error_response("RECOVERY_CODE_INVALID", recovery_service.GENERIC_RECOVERY_MESSAGE, 400)
    try:
        token = recovery_service.consume_recovery_code(identifier[1], payload.get("code"))
    except RecoveryError as exc:
        return error_response(exc.code, exc.message, exc.status)
    return success_response("Code accepted.", {"resetToken": token})


@recovery_bp.post("/recovery/request")
@limiter.limit("5 per hour")
def recovery_request():
    payload = _json_object()
    if payload is None:
        return _invalid_json()
    try:
        reference = recovery_service.submit_recovery_request(payload)
    except RecoveryError as exc:
        return error_response(exc.code, exc.message, exc.status)
    return success_response(
        "Request received. Nothing changes on your account until ownership is verified.",
        {"ref": reference},
        status=201,
    )


@recovery_bp.post("/auth/recovery-codes")
@login_required
@limiter.limit("5 per hour")
def generate_codes():
    payload = _json_object()
    if payload is None:
        return _invalid_json()
    if not recovery_service.verify_current_password(current_user, payload.get("password")):
        # Re-entering the password stops a stolen session from creating codes on its own.
        return error_response("INVALID_PASSWORD", "That password is not correct.", 400)
    codes = recovery_service.generate_recovery_codes(current_user)
    return success_response(
        "Save these codes somewhere safe. Each works once, and they will not be shown again.",
        {"codes": codes},
    )


@recovery_bp.get("/admin/recovery-requests")
@login_required
@roles_required(UserRole.ADMIN)
def admin_recovery_requests():
    return success_response("Recovery requests", {"requests": recovery_service.list_recovery_requests()})
