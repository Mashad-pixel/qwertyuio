"""Changes to the signed-in account's own password and email.

Both changes require the current password, so a stolen session cookie alone cannot take over an
account. After either change, every other session is signed out; the session making the change
stays signed in.
"""

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.user import User
from app.security.account_rules import is_valid_email, normalize_email, password_problem
from app.services.errors import OrderError
from app.services.session_service import revoke_other_sessions
from app.services.time_utils import utcnow

WRONG_PASSWORD_MESSAGE = "Your current password is not correct."


def change_password(user, current_password, new_password):
    """Set a new password. Returns how many other sessions were signed out."""
    if not user.check_password(current_password):
        raise OrderError("CURRENT_PASSWORD_INCORRECT", WRONG_PASSWORD_MESSAGE, 400)

    problem = password_problem(new_password)
    if problem:
        raise OrderError("INVALID_PASSWORD", problem, 400)
    if user.check_password(new_password):
        raise OrderError("PASSWORD_UNCHANGED", "Choose a password that is different from your current one.", 400)

    user.set_password(new_password)
    user.password_changed_at = utcnow()
    db.session.commit()
    return revoke_other_sessions(user.id)


def change_email(user, current_password, new_email):
    """Change the sign-in email. Returns the normalized new address."""
    if not user.check_password(current_password):
        raise OrderError("CURRENT_PASSWORD_INCORRECT", WRONG_PASSWORD_MESSAGE, 400)

    email = normalize_email(new_email)
    if not is_valid_email(email):
        raise OrderError("INVALID_EMAIL", "Enter a valid email address.", 400)
    if email == user.email:
        raise OrderError("EMAIL_UNCHANGED", "That is already your sign-in email.", 400)
    if User.query.filter(User.email == email, User.id != user.id).first() is not None:
        raise OrderError("EMAIL_UNAVAILABLE", "An account with this email already exists.", 409)

    user.email = email
    try:
        db.session.commit()
    except IntegrityError:
        # The unique constraint also protects against two changes racing to the same address.
        db.session.rollback()
        raise OrderError("EMAIL_UNAVAILABLE", "An account with this email already exists.", 409)

    revoke_other_sessions(user.id)
    return email
