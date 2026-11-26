from flask import Blueprint, current_app, request
from flask_login import current_user, login_required

from app.extensions import limiter
from app.models.user import UserRole
from app.responses import error_response, success_response
from app.security.permissions import roles_required
from app.security.rate_limit import user_rate_key
from app.services.errors import OrderError
from app.services.presence_service import (
    build_presence_link,
    issue_display_token,
    public_presence_settings,
    render_qr_svg,
    revoke_active_tokens,
    verify_presence,
)
from app.services.time_utils import as_utc

presence_bp = Blueprint("presence", __name__, url_prefix="/api/presence")

# Only staff screens may display live QR codes. Students and anonymous users may not.
SCREEN_ACCESS = (UserRole.ADMIN, UserRole.KITCHEN)


def _order_error(exc):
    return error_response(exc.code, exc.message, exc.status)


def _public_base_url():
    # Production requires PUBLIC_BASE_URL (validated at startup). Development falls back to the request host.
    configured = current_app.config.get("PUBLIC_BASE_URL") or ""
    return configured or request.host_url


@presence_bp.route("/settings", methods=["GET"])
def settings():
    """Public, non-sensitive settings for the student page. Coordinates are never returned."""
    return success_response("Presence settings", public_presence_settings())


@presence_bp.route("/display-code", methods=["GET"])
@login_required
@roles_required(*SCREEN_ACCESS)
@limiter.limit("30 per minute", key_func=user_rate_key)
def display_code():
    """Return a freshly issued QR code (SVG) for the authorized canteen screen."""
    try:
        raw_token, expires_at = issue_display_token(current_user.id)
    except OrderError as exc:
        return _order_error(exc)

    svg = render_qr_svg(build_presence_link(raw_token, _public_base_url()))

    response, status = success_response("Canteen code issued", {
        "qr_svg": svg,
        "ttl_seconds": current_app.config["PRESENCE_TOKEN_TTL_SECONDS"],
        "expires_at": as_utc(expires_at).isoformat(),
    })
    response.headers["Cache-Control"] = "no-store"
    return response, status


@presence_bp.route("/revoke", methods=["POST"])
@login_required
@roles_required(*SCREEN_ACCESS)
@limiter.limit("10 per minute", key_func=user_rate_key)
def revoke():
    """Stop every live canteen code immediately, for example if a screen is compromised."""
    count = revoke_active_tokens(current_user.id)
    return success_response("Live canteen codes revoked", {"revoked": count})


@presence_bp.route("/verify", methods=["POST"])
@login_required
@roles_required(UserRole.STUDENT)
@limiter.limit("10 per minute", key_func=user_rate_key)
def verify():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("INVALID_JSON", "Request body must be a JSON object.", 400)

    try:
        raw_session, expires_at = verify_presence(
            student_id=current_user.id,
            raw_token=payload.get("token"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            accuracy=payload.get("accuracy"),
            timestamp_ms=payload.get("timestamp"),
        )
    except OrderError as exc:
        return _order_error(exc)

    response, status = success_response("You are verified at the canteen", {
        "session_token": raw_session,
        "expires_at": as_utc(expires_at).isoformat(),
        "expires_in_seconds": current_app.config["PRESENCE_SESSION_TTL_SECONDS"],
        "single_use": True,
    }, 201)
    response.headers["Cache-Control"] = "no-store"
    return response, status
