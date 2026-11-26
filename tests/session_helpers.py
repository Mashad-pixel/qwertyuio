"""Create real server-side sessions for tests.

Session-based tests need a live user_sessions row, the same as a real login produces.
Call this inside a session_transaction block and store the result under the "sid" key.
"""

import secrets
from datetime import timedelta

from app.extensions import db
from app.models.user_session import UserSession
from app.services.session_service import hash_token
from app.services.time_utils import utcnow


def issue_test_session(user, mfa_verified=True):
    token = secrets.token_urlsafe(32)
    now = utcnow()
    row = UserSession(
        token_hash=hash_token(token),
        user_id=user.id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=12),
        mfa_verified=mfa_verified,
    )
    db.session.add(row)
    db.session.commit()
    return token
