"""Test helpers for presence verification.

These create verified sessions directly in the database, without GPS. They exist so that
order, payment and kitchen tests can focus on their own behaviour. Production code has no
equivalent path. tests/test_presence.py covers the real verification route.
"""
import secrets
from datetime import timedelta

from app.extensions import db
from app.models.presence import PresenceRedemption, PresenceSession, PresenceToken
from app.services.order_service import create_order as _create_order
from app.services.presence_service import hash_session, hash_token
from app.services.time_utils import utcnow


def issue_test_presence_session(student_id, *, expires_at=None):
    """Create a valid (or, with expires_at in the past, expired) single-use session.

    Returns the raw session token the student would send in X-Presence-Session.
    """
    now = utcnow()
    raw_token = secrets.token_urlsafe(32)
    token = PresenceToken(
        token_hash=hash_token(raw_token),
        issued_by_id=student_id,
        issued_at=now,
        expires_at=now + timedelta(seconds=10),
    )
    db.session.add(token)
    db.session.flush()

    redemption = PresenceRedemption(
        token_id=token.id,
        student_id=student_id,
        redeemed_at=now,
        distance_meters=0,
        accuracy_meters=5,
    )
    db.session.add(redemption)
    db.session.flush()

    raw_session = secrets.token_urlsafe(32)
    db.session.add(PresenceSession(
        session_hash=hash_session(raw_session),
        student_id=student_id,
        redemption_id=redemption.id,
        created_at=now,
        expires_at=expires_at or (now + timedelta(seconds=180)),
    ))
    db.session.commit()
    return raw_session


def presence_headers_for(client):
    """Headers carrying a fresh verified presence session for the student logged into `client`."""
    with client.session_transaction() as sess:
        user_id = sess.get("_user_id")
    if user_id is None:  # Anonymous: send nothing, so the server's login check answers.
        return {}
    return {"X-Presence-Session": issue_test_presence_session(int(user_id))}


def create_order_for(student_id, raw_items, idempotency_key=None, *, presence_session_token=None):
    """Drop-in replacement for the service's create_order() in tests.

    Supplies a fresh verified session unless the caller passes one.
    """
    token = presence_session_token or issue_test_presence_session(student_id)
    return _create_order(
        student_id,
        raw_items,
        idempotency_key=idempotency_key,
        presence_session_token=token,
    )
