"""Server-side login sessions.

Flask-Login stores the user id in a signed cookie, which the server cannot revoke. This
service adds a row per login in user_sessions. A request is accepted only while its row
exists, is not revoked, and is inside both the idle and absolute lifetimes for the user's
role. Privileged roles get much shorter lifetimes than students.
"""

import hashlib
import secrets
from datetime import timedelta

from flask import current_app, session
from sqlalchemy import or_

from app.extensions import db
from app.models.user import UserRole
from app.models.user_session import UserSession
from app.services.time_utils import as_utc, utcnow

SESSION_KEY = "sid"
# Idle time is refreshed at most this often, so a busy session doesn't write on every request.
_TOUCH_INTERVAL = timedelta(seconds=60)
_PRIVILEGED_ROLES = (UserRole.ADMIN, UserRole.KITCHEN)


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _lifetimes(role):
    config = current_app.config
    if role in _PRIVILEGED_ROLES:
        return (
            timedelta(minutes=config["SESSION_IDLE_MINUTES_PRIVILEGED"]),
            timedelta(hours=config["SESSION_ABSOLUTE_HOURS_PRIVILEGED"]),
        )
    return (
        timedelta(minutes=config["SESSION_IDLE_MINUTES_STUDENT"]),
        timedelta(hours=config["SESSION_ABSOLUTE_HOURS_STUDENT"]),
    )


def _current_row():
    token = session.get(SESSION_KEY)
    if not isinstance(token, str) or not token:
        return None
    return db.session.get(UserSession, hash_token(token))


def start_session(user, mfa_verified):
    """Create a session for a user who has just authenticated, and bind it to this browser.

    Callers must clear the Flask session before calling this, to prevent session fixation.
    """
    token = secrets.token_urlsafe(32)
    now = utcnow()
    _, absolute = _lifetimes(user.role)
    row = UserSession(
        token_hash=hash_token(token),
        user_id=user.id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + absolute,
        mfa_verified=bool(mfa_verified),
    )
    db.session.add(row)
    db.session.commit()
    session[SESSION_KEY] = token
    # Students keep the cookie across browser restarts. Privileged sessions end with the browser.
    session.permanent = user.role not in _PRIVILEGED_ROLES
    return row


def validate_session_for(user):
    """Return this request's live session row for the user, or None.

    A session that has expired or sat idle too long is revoked here, so it stays dead even
    if the cookie comes back later.
    """
    row = _current_row()
    if row is None or row.user_id != user.id or row.revoked_at is not None:
        return None

    now = utcnow()
    idle, _ = _lifetimes(user.role)
    expires_at = as_utc(row.expires_at)
    last_seen = as_utc(row.last_seen_at)
    if now >= expires_at or now - last_seen > idle:
        row.revoked_at = now
        db.session.commit()
        return None

    if now - last_seen >= _TOUCH_INTERVAL:
        row.last_seen_at = now
        db.session.commit()
    return row


def current_session_mfa_verified():
    """True if this browser's live session has passed the second factor."""
    row = _current_row()
    if row is None or row.revoked_at is not None or not row.mfa_verified:
        return False
    return as_utc(row.expires_at) > utcnow()


def mark_current_session_mfa_verified():
    row = _current_row()
    if row is not None and row.revoked_at is None:
        row.mfa_verified = True
        db.session.commit()
    return row


def revoke_current_session():
    row = _current_row()
    if row is not None and row.revoked_at is None:
        row.revoked_at = utcnow()
        db.session.commit()


def revoke_user_sessions(user_id):
    """End every live session for a user. Returns how many were revoked."""
    count = (
        UserSession.query
        .filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .update({"revoked_at": utcnow()}, synchronize_session="fetch")
    )
    db.session.commit()
    return count


def prune_sessions():
    """Delete expired and revoked session rows. Returns how many were removed."""
    now = utcnow()
    count = (
        UserSession.query
        .filter(or_(UserSession.expires_at < now, UserSession.revoked_at.isnot(None)))
        .delete(synchronize_session="fetch")
    )
    db.session.commit()
    return count
