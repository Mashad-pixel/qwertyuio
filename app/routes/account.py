"""Signed-in account: profile, password and email changes, and session controls.

Every route needs a live session. Administrators also need their second factor (enforced for all
endpoints that are not exempt, in app/__init__.py).
"""

from flask import Blueprint, request
from flask_login import current_user, login_required

from app.extensions import db, limiter
from app.models.user import User
from app.responses import error_response, success_response
from app.security.rate_limit import user_rate_key
from app.services import account_service
from app.services.errors import OrderError
from app.services.session_service import current_session_token_hash, list_user_sessions, revoke_other_sessions

account_bp = Blueprint("account", __name__, url_prefix="/api/account")


def _json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _order_error(exc):
    return error_response(exc.code, exc.message, exc.status)


def _iso(value):
    return value.isoformat() if value is not None else None


@account_bp.get("")
@login_required
def account_profile():
    user = db.session.get(User, current_user.id)
    return success_response("Account retrieved", {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "mfa_enabled": bool(user.mfa_enabled),
        "password_changed_at": _iso(user.password_changed_at),
    })


@account_bp.post("/password")
@login_required
@limiter.limit("10 per 15 minutes", key_func=user_rate_key)
def change_password():
    payload = _json_object()
    if payload is None:
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    current = payload.get("current_password")
    new = payload.get("new_password")
    if not isinstance(current, str) or not isinstance(new, str) or not current or not new:
        return error_response("MISSING_FIELDS", "Enter your current password and a new password.", 400)

    user = db.session.get(User, current_user.id)
    try:
        signed_out = account_service.change_password(user, current, new)
    except OrderError as exc:
        return _order_error(exc)
    return success_response(
        "Password changed. Other devices have been signed out.",
        {"signed_out_other_sessions": signed_out},
    )


@account_bp.post("/email")
@login_required
@limiter.limit("10 per 15 minutes", key_func=user_rate_key)
def change_email():
    payload = _json_object()
    if payload is None:
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    current = payload.get("current_password")
    new_email = payload.get("new_email")
    if not isinstance(current, str) or not isinstance(new_email, str) or not current or not new_email:
        return error_response("MISSING_FIELDS", "Enter your current password and the new email address.", 400)

    user = db.session.get(User, current_user.id)
    try:
        email = account_service.change_email(user, current, new_email)
    except OrderError as exc:
        return _order_error(exc)
    return success_response("Email address changed.", {"email": email})


@account_bp.get("/sessions")
@login_required
def list_sessions():
    current = current_session_token_hash()
    rows = list_user_sessions(current_user.id)
    return success_response("Sessions retrieved", {
        "sessions": [
            {
                "created_at": _iso(row.created_at),
                "last_seen_at": _iso(row.last_seen_at),
                "expires_at": _iso(row.expires_at),
                "mfa_verified": bool(row.mfa_verified),
                "current": row.token_hash == current,
            }
            for row in rows
        ]
    })


@account_bp.post("/sessions/revoke-others")
@login_required
def revoke_sessions_except_this_one():
    revoked = revoke_other_sessions(current_user.id)
    return success_response("Other sessions signed out.", {"revoked": revoked})
