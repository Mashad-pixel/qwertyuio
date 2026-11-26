from flask_limiter.util import get_remote_address
from flask_login import current_user


def user_rate_key():
    """Rate-limit per logged-in account, falling back to IP for anonymous requests.

    Every student on campus Wi-Fi shares one public IP. Keying on the account stops one
    student's usage from locking out the others. IP addresses are never used as location.
    """
    if current_user.is_authenticated:
        return f"user:{current_user.get_id()}"
    return get_remote_address()
