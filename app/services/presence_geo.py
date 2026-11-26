"""Pure helpers for presence verification: geofence maths, GPS sample checks and keyed hashing.

Nothing in this module touches Flask, the database or the clock, so it can be unit tested
directly. All time values are passed in explicitly.
"""

import hashlib
import hmac
import math
import re

# Mean Earth radius (IUGG). Good to well under a metre at canteen scale.
EARTH_RADIUS_METERS = 6371008.8

# QR tokens are secrets.token_urlsafe(32) (43 characters). Accept a wider range, reject junk.
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")

# A GPS timestamp may be at most this far in the future (device clock skew allowance).
MAX_FUTURE_SKEW_SECONDS = 30


def haversine_meters(lat1, lon1, lat2, lon2):
    """Great-circle distance between two WGS-84 points, in metres."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    # Clamp against floating-point drift so sqrt never receives a value outside [0, 1].
    a = min(1.0, max(0.0, a))
    return 2 * EARTH_RADIUS_METERS * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def is_finite_number(value):
    """True for real int/float values. Rejects bools, strings, NaN and infinity."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate_location_sample(latitude, longitude, accuracy, timestamp_ms, now_ms,
                             max_accuracy_meters, max_age_seconds):
    """Check one browser GPS reading before it is used.

    Returns None when the sample is usable, otherwise a (code, message) tuple.
    The caller turns that into the API error response.
    """
    if not (is_finite_number(latitude) and is_finite_number(longitude)):
        return "LOCATION_INVALID", "Your location could not be read. Try again."
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return "LOCATION_INVALID", "Your location could not be read. Try again."

    if not is_finite_number(accuracy) or accuracy <= 0:
        return "LOCATION_INVALID", "Your location could not be read. Try again."

    if not is_finite_number(timestamp_ms):
        return "LOCATION_INVALID", "Your location could not be read. Try again."

    age_seconds = (now_ms - timestamp_ms) / 1000.0
    if age_seconds < -MAX_FUTURE_SKEW_SECONDS:
        return "LOCATION_INVALID", "Your device clock looks incorrect. Check the date and time, then try again."
    if age_seconds > max_age_seconds:
        return "LOCATION_STALE", "That location reading is too old. Tap Verify location again."

    if accuracy > max_accuracy_meters:
        return (
            "LOCATION_ACCURACY_TOO_LOW",
            f"Your GPS signal is too weak (about {int(round(accuracy))} m). "
            "Move near a window or outdoors, then try again.",
        )

    return None


def keyed_digest(secret_key, purpose, raw_value):
    """HMAC-SHA256 of a random token, keyed with the app secret and separated by purpose.

    The database stores only this digest. A leaked table cannot be replayed without the
    server secret, and a token issued for one purpose cannot be used for another.
    """
    key = secret_key.encode("utf-8")
    message = f"trayup:{purpose}:v1:{raw_value}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()
