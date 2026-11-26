"""Startup checks for the production configuration.

The application refuses to start in production when any of these fail, instead of
starting with a weaker setting that someone might not notice.
"""

from app.security.url_rules import normalize_allowed_hosts

MIN_SECRET_KEY_LENGTH = 32
SHARED_RATE_LIMIT_SCHEMES = ("redis://", "rediss://")


def production_problems(config, dev_secret_key):
    """Return a list of human-readable problems. An empty list means the config is acceptable."""
    problems = []

    secret_key = config.get("SECRET_KEY")
    if not isinstance(secret_key, str) or len(secret_key) < MIN_SECRET_KEY_LENGTH or secret_key == dev_secret_key:
        problems.append(
            f"SECRET_KEY must be a unique value of at least {MIN_SECRET_KEY_LENGTH} characters."
        )

    storage_uri = config.get("RATELIMIT_STORAGE_URI")
    if not isinstance(storage_uri, str) or not storage_uri.startswith(SHARED_RATE_LIMIT_SCHEMES):
        problems.append(
            "RATELIMIT_STORAGE_URI must point to shared storage (redis:// or rediss://). "
            "In-memory counters are not shared between instances and reset on restart."
        )

    if not config.get("SESSION_COOKIE_SECURE"):
        problems.append("SESSION_COOKIE_SECURE must be enabled in production.")

    if config.get("DEBUG"):
        problems.append("DEBUG must be disabled in production.")

    # Recovery codes are sent by email. The console and memory backends would leak them.
    if config.get("MAIL_BACKEND") in ("console", "memory"):
        problems.append("MAIL_BACKEND must be 'smtp' in production; other backends do not deliver email.")

    try:
        normalize_allowed_hosts(config.get("MENU_IMAGE_ALLOWED_HOSTS", ()))
    except ValueError as exc:
        problems.append(str(exc))

    return problems
