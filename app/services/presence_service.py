"""Live QR + GPS presence verification.

Flow:
  1. A staff screen (ADMIN or KITCHEN) shows a QR code built from a random token that expires
     after PRESENCE_TOKEN_TTL_SECONDS (10 s by default).
  2. A student scans it, which opens the verify page. The student then taps Verify location.
     The browser asks for permission and sends one GPS reading.
  3. verify_presence() checks the token, the GPS sample and the geofence on the server. On
     success it records one redemption for that student and issues a single-use session token
     that lasts PRESENCE_SESSION_TTL_SECONDS (180 s by default).
  4. POST /api/orders must present that session. create_order() consumes it in the same
     database transaction that creates the order, so it can authorise exactly one order.

Only keyed digests of tokens and sessions are stored. GPS coordinates are never stored.
"""

import io
import math
import secrets
from datetime import timedelta

from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.presence import PresenceRedemption, PresenceSession, PresenceToken
from app.services.errors import OrderError
from app.services.presence_geo import (
    TOKEN_PATTERN,
    haversine_meters,
    keyed_digest,
    validate_location_sample,
)
from app.services.time_utils import as_utc, utcnow

# Path served by Flask (see app/routes/frontend.py). The QR code links here.
PRESENCE_PAGE_PATH = "/frontend/student/verify.html"


def _settings():
    """Read presence settings. Raises a 503 when the canteen location is not configured."""
    cfg = current_app.config
    latitude = cfg.get("CANTEEN_LATITUDE")
    longitude = cfg.get("CANTEEN_LONGITUDE")
    if latitude is None or longitude is None:
        raise OrderError(
            "PRESENCE_NOT_CONFIGURED",
            "Ordering is unavailable because the canteen location has not been configured.",
            503,
        )
    return {
        "latitude": latitude,
        "longitude": longitude,
        "radius_meters": cfg["PRESENCE_RADIUS_METERS"],
        "max_accuracy_meters": cfg["PRESENCE_MAX_ACCURACY_METERS"],
        "gps_max_age_seconds": cfg["PRESENCE_GPS_MAX_AGE_SECONDS"],
        "token_ttl_seconds": cfg["PRESENCE_TOKEN_TTL_SECONDS"],
        "session_ttl_seconds": cfg["PRESENCE_SESSION_TTL_SECONDS"],
    }


def hash_token(raw_token):
    return keyed_digest(current_app.config["SECRET_KEY"], "presence-token", raw_token)


def hash_session(raw_session):
    return keyed_digest(current_app.config["SECRET_KEY"], "presence-session", raw_session)


def public_presence_settings():
    """Non-sensitive values the student page needs to show its notices. No coordinates."""
    cfg = current_app.config
    configured = cfg.get("CANTEEN_LATITUDE") is not None and cfg.get("CANTEEN_LONGITUDE") is not None
    return {
        "configured": configured,
        "radius_meters": cfg["PRESENCE_RADIUS_METERS"],
        "max_accuracy_meters": cfg["PRESENCE_MAX_ACCURACY_METERS"],
        "token_ttl_seconds": cfg["PRESENCE_TOKEN_TTL_SECONDS"],
        "session_ttl_seconds": cfg["PRESENCE_SESSION_TTL_SECONDS"],
    }


def issue_display_token(issued_by_id):
    """Create a fresh random token for the canteen screen. Returns (raw_token, expires_at)."""
    settings = _settings()
    now = utcnow()
    raw_token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(seconds=settings["token_ttl_seconds"])

    try:
        db.session.add(PresenceToken(
            token_hash=hash_token(raw_token),
            issued_by_id=issued_by_id,
            issued_at=now,
            expires_at=expires_at,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return raw_token, expires_at


def build_presence_link(raw_token, base_url):
    # The token sits in the URL fragment, so it is never sent to a web server or written to logs.
    return f"{base_url.rstrip('/')}{PRESENCE_PAGE_PATH}#presence={raw_token}"


def render_qr_svg(text):
    """Return the QR code for `text` as an inline SVG string."""
    import qrcode
    from qrcode.image.svg import SvgPathImage

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)

    buffer = io.BytesIO()
    image.save(buffer)
    svg = buffer.getvalue().decode("utf-8")
    # Drop the XML declaration so the markup can be inserted straight into the page.
    return svg[svg.index("<svg"):]


def verify_presence(student_id, raw_token, latitude, longitude, accuracy, timestamp_ms):
    """Check a QR token and one GPS reading. On success create a single-use session.

    Returns (raw_session_token, session_expires_at). Raises OrderError otherwise.
    Nothing is written unless every check passes.
    """
    settings = _settings()
    now = utcnow()

    if not isinstance(raw_token, str) or not TOKEN_PATTERN.match(raw_token):
        raise OrderError(
            "INVALID_QR_CODE",
            "This QR code is not valid. Scan the code shown on the canteen screen.",
            400,
        )

    problem = validate_location_sample(
        latitude,
        longitude,
        accuracy,
        timestamp_ms,
        now_ms=int(now.timestamp() * 1000),
        max_accuracy_meters=settings["max_accuracy_meters"],
        max_age_seconds=settings["gps_max_age_seconds"],
    )
    if problem is not None:
        code, message = problem
        raise OrderError(code, message, 400)

    distance = haversine_meters(latitude, longitude, settings["latitude"], settings["longitude"])
    session_expires_at = now + timedelta(seconds=settings["session_ttl_seconds"])

    try:
        token = PresenceToken.query.filter_by(token_hash=hash_token(raw_token)).first()
        if token is None:
            raise OrderError(
                "INVALID_QR_CODE",
                "This QR code is not valid. Scan the code shown on the canteen screen.",
                400,
            )
        if token.revoked_at is not None:
            raise OrderError(
                "QR_CODE_REVOKED",
                "This QR code is no longer active. Scan the code currently shown on the screen.",
                409,
            )
        if as_utc(token.expires_at) <= now:
            raise OrderError(
                "QR_CODE_EXPIRED",
                "This QR code has expired. Scan the code currently shown on the screen.",
                409,
            )
        if distance > settings["radius_meters"]:
            raise OrderError(
                "OUTSIDE_CANTEEN_AREA",
                f"You need to be within {int(settings['radius_meters'])} m of the canteen to order.",
                403,
            )

        redemption = PresenceRedemption(
            token_id=token.id,
            student_id=student_id,
            redeemed_at=now,
            distance_meters=int(round(distance)),
            accuracy_meters=int(math.ceil(accuracy)),
        )
        db.session.add(redemption)
        # The unique (token, student) constraint fails here if this student already used this code.
        db.session.flush()

        raw_session = secrets.token_urlsafe(32)
        db.session.add(PresenceSession(
            session_hash=hash_session(raw_session),
            student_id=student_id,
            redemption_id=redemption.id,
            created_at=now,
            expires_at=session_expires_at,
        ))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise OrderError(
            "QR_CODE_ALREADY_USED",
            "You have already used this QR code. Scan the code currently shown on the screen.",
            409,
        )
    except Exception:
        db.session.rollback()
        raise

    return raw_session, session_expires_at


def load_presence_session_for_order(raw_session, student_id, now):
    """Read-only checks that run before an order is priced. Returns the session row id."""
    if raw_session is None or raw_session == "":
        raise OrderError(
            "PRESENCE_VERIFICATION_REQUIRED",
            "Verify that you are at the canteen before placing an order.",
            403,
        )
    if not isinstance(raw_session, str) or not TOKEN_PATTERN.match(raw_session):
        raise OrderError(
            "PRESENCE_SESSION_INVALID",
            "Your location verification is not valid. Verify again to order.",
            403,
        )

    row = PresenceSession.query.filter_by(session_hash=hash_session(raw_session)).first()
    # A session belonging to someone else is reported exactly like an unknown one.
    if row is None or row.student_id != student_id:
        raise OrderError(
            "PRESENCE_SESSION_INVALID",
            "Your location verification is not valid. Verify again to order.",
            403,
        )
    if row.consumed_at is not None:
        raise OrderError(
            "PRESENCE_SESSION_USED",
            "This verification has already been used for an order. Verify again to order.",
            409,
        )
    if as_utc(row.expires_at) <= now:
        raise OrderError(
            "PRESENCE_SESSION_EXPIRED",
            "Your verification has expired. Verify again to order.",
            403,
        )
    return row.id


def consume_presence_session(session_id, student_id, order_id, now):
    """Mark the session used by this order, atomically.

    Must run inside the order transaction. A conditional UPDATE means that if two requests
    race on one session, only one row changes. The loser raises and rolls back.
    """
    updated = (
        PresenceSession.query.filter(
            PresenceSession.id == session_id,
            PresenceSession.student_id == student_id,
            PresenceSession.consumed_at.is_(None),
            PresenceSession.expires_at > now,
        ).update(
            {"consumed_at": now, "order_id": order_id},
            synchronize_session=False,
        )
    )
    if updated != 1:
        raise OrderError(
            "PRESENCE_SESSION_USED",
            "This verification was already used or has expired. Verify again to order.",
            409,
        )


def revoke_active_tokens(staff_user_id):
    """Stop every QR code that is still live. Returns how many were revoked."""
    now = utcnow()
    try:
        count = (
            PresenceToken.query.filter(
                PresenceToken.revoked_at.is_(None),
                PresenceToken.expires_at > now,
            ).update({"revoked_at": now}, synchronize_session=False)
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    current_app.logger.info("Revoked %d live presence code(s) (staff user %s).", count, staff_user_id)
    return count


def prune_presence_records(now=None):
    """Delete verification records older than PRESENCE_RETENTION_DAYS.

    Deletes children first (sessions, then redemptions, then tokens), so this works even when
    SQLite does not enforce foreign keys. Returns the number of rows removed per table.
    """
    now = now or utcnow()
    cutoff = now - timedelta(days=current_app.config["PRESENCE_RETENTION_DAYS"])
    try:
        sessions = PresenceSession.query.filter(PresenceSession.created_at < cutoff).delete(synchronize_session=False)
        redemptions = PresenceRedemption.query.filter(PresenceRedemption.redeemed_at < cutoff).delete(synchronize_session=False)
        # Remove a token only when it is old and no kept redemption still refers to it.
        still_referenced = select(PresenceRedemption.token_id)
        tokens = (
            PresenceToken.query
            .filter(PresenceToken.issued_at < cutoff, PresenceToken.id.not_in(still_referenced))
            .delete(synchronize_session=False)
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return {"sessions": sessions, "redemptions": redemptions, "tokens": tokens}
