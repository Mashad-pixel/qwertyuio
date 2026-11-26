"""Rules for menu image URLs.

Images are loaded by students' browsers, so a menu item can make a browser contact any
host it names. These rules keep that contact to HTTPS, to hosts an administrator has
explicitly approved, and to the default port.
"""

import re
from urllib.parse import urlsplit

LOCAL_IMAGE_PREFIX = "/static/"
DEFAULT_HTTPS_PORT = 443
_HOSTNAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")
_UNSAFE_CHARACTERS = re.compile(r"[\x00-\x1f\x7f\s\\\"'<>`]")

IMAGE_URL_RULE_MESSAGE = (
    "Must be a /static/ path or an https:// link to an approved image host."
)


def normalize_allowed_hosts(hosts):
    """Return a clean, lowercase set of hostnames. Anything malformed raises ValueError."""
    cleaned = set()
    for raw in hosts or ():
        host = str(raw).strip().lower()
        if not host:
            continue
        if not _HOSTNAME_PATTERN.fullmatch(host):
            raise ValueError(f"Invalid image host in allowlist: {raw!r}")
        cleaned.add(host)
    return frozenset(cleaned)


def image_url_problem(value, allowed_hosts):
    """Return an error message if the image URL is not acceptable, otherwise None."""
    if not isinstance(value, str):
        return IMAGE_URL_RULE_MESSAGE
    if _UNSAFE_CHARACTERS.search(value):
        return "Image URL must not contain spaces, quotes, angle brackets, backslashes or control characters."

    if value.startswith(LOCAL_IMAGE_PREFIX):
        return None

    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return IMAGE_URL_RULE_MESSAGE

    if parts.scheme != "https":
        return "Image URLs must use https://."
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return "Image URLs must not contain user credentials."
    if port not in (None, DEFAULT_HTTPS_PORT):
        return "Image URLs must use the default HTTPS port."

    hostname = (parts.hostname or "").lower()
    if not hostname or hostname not in normalize_allowed_hosts(allowed_hosts):
        return "Image host is not on the approved list."
    return None
