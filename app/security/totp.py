"""Time-based one-time passwords (RFC 6238) using only the standard library.

Codes are 6 digits, derived from HMAC-SHA1 over a 30-second time step. Verification
accepts the current step and one step either side to allow for clock drift, and it
refuses any step at or before the last step that was accepted, so a code cannot be
replayed.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

TIME_STEP_SECONDS = 30
DIGITS = 6
DRIFT_STEPS = 1
SECRET_BYTES = 20  # 160 bits, the RFC 4226 recommendation for HMAC-SHA1.


def generate_secret():
    """Return a new random base32 secret (no padding)."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode("ascii").rstrip("=")


def _decode_secret(secret):
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * (-len(normalized) % 8)
    return base64.b32decode(normalized + padding, casefold=True)


def code_at(secret, counter, digits=DIGITS):
    """Return the code for a given time-step counter."""
    key = _decode_secret(secret)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** digits)).zfill(digits)


def current_counter(now=None):
    timestamp = time.time() if now is None else now
    return int(timestamp // TIME_STEP_SECONDS)


def verify_code(secret, code, last_used_step=None, now=None):
    """Return the accepted time step if the code is valid and new, otherwise None."""
    if not secret or not isinstance(code, str) or len(code) != DIGITS or not code.isdigit():
        return None
    counter = current_counter(now)
    for candidate in range(counter - DRIFT_STEPS, counter + DRIFT_STEPS + 1):
        if candidate < 0:
            continue
        if last_used_step is not None and candidate <= last_used_step:
            continue
        if hmac.compare_digest(code_at(secret, candidate), code):
            return candidate
    return None


def provisioning_uri(secret, account_name, issuer="TrayUP"):
    """Return an otpauth:// URI that authenticator apps can import."""
    label = quote(f"{issuer}:{account_name}", safe="@:")
    query = urlencode({
        "secret": secret,
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": DIGITS,
        "period": TIME_STEP_SECONDS,
    })
    return f"otpauth://totp/{label}?{query}"
