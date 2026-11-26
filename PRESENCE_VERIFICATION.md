# Live QR + GPS presence verification

Students can order only while they are physically at the canteen. A staff screen shows a live QR code
that changes every 10 seconds. A student scans it, taps **Verify my location**, and gets a single-use
session valid for 180 seconds. The order API refuses any order without that session.

The static canteen QR (menu browsing) and the order-collection QR are unchanged.

## What is enforced where

| Layer | Rule |
|---|---|
| Staff screen | Only ADMIN or KITCHEN accounts can display live codes or revoke them. |
| QR token | `secrets.token_urlsafe(32)`, valid for `PRESENCE_TOKEN_TTL_SECONDS` (10 s). Only a keyed HMAC-SHA256 digest is stored. |
| Student | Only STUDENT accounts can verify. Each (token, student) pair can be redeemed once. Many students may share one live code. |
| GPS | One reading, sent only when the student taps Verify. Must have accuracy ≤ 75 m, be at most 60 s old, and be within 100 m (Haversine) of the configured canteen point. Coordinates are never stored. |
| Session | Random, 180 s, bound to one student, and consumed in the same database transaction as the order. A failed order does not consume it. |
| Order API | `POST /api/orders` requires `X-Presence-Session`. Direct API calls, screenshots and edited frontends cannot skip it. |
| Startup | Production refuses to start without `CANTEEN_LATITUDE`, `CANTEEN_LONGITUDE` and an `https://` `PUBLIC_BASE_URL`. |

Honest limits: a screenshot of a live code works for up to 10 seconds and only from inside the geofence.
GPS can be spoofed, and no client-side or server-side check removes that risk entirely. The design makes
captured codes and remote ordering much less useful. It does not make them impossible.

## Setup

```bash
pip install -r requirements.txt          # adds qrcode>=7.4
flask --app run db upgrade               # applies d8e9f0a1b2c3_add_presence_verification
```

Add to `.env` (see `.env.example`):

```dotenv
CANTEEN_LATITUDE=<surveyed latitude>
CANTEEN_LONGITUDE=<surveyed longitude>
PUBLIC_BASE_URL=https://your-domain.example
```

Do not guess coordinates. Measure them at the canteen entrance. Without them, ordering is unavailable
(503 `PRESENCE_NOT_CONFIGURED`) and production will not start.

Create staff accounts as before (`flask --app run create-user ...`). Students create their own accounts at
`/frontend/student/login.html`, or staff can create them with `--role STUDENT`.

## Running the screens

- Staff: sign in at `/frontend/kitchen/login.html`, then open `/frontend/kitchen/presence-display.html` on the canteen screen.
- Students: scan the code, which opens `/frontend/student/verify.html#presence=…`. Students can also open the page and use the camera button if their browser supports `BarcodeDetector`.

## Retention

Verification records are kept for `PRESENCE_RETENTION_DAYS` (default 7). Run this daily:

```bash
flask --app run prune-presence
```

## Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/presence/settings` | Public | Radius, accuracy limit, TTLs. No coordinates. |
| GET | `/api/presence/display-code` | ADMIN, KITCHEN | New QR code as SVG, plus `ttl_seconds`. |
| POST | `/api/presence/revoke` | ADMIN, KITCHEN | Revoke all live codes. |
| POST | `/api/presence/verify` | STUDENT | Body: `token`, `latitude`, `longitude`, `accuracy`, `timestamp`. Returns the session token (201). |
| POST | `/api/orders` | STUDENT | Requires header `X-Presence-Session`. |
| POST | `/api/auth/register` | Public | Creates a STUDENT account and signs in. Rate-limited. |
| GET | `/frontend/<path>` | Public | Serves the static frontend. |

Error codes: `PRESENCE_VERIFICATION_REQUIRED`, `PRESENCE_SESSION_INVALID`, `PRESENCE_SESSION_EXPIRED`,
`PRESENCE_SESSION_USED`, `QR_CODE_EXPIRED`, `QR_CODE_REVOKED`, `QR_CODE_ALREADY_USED`, `INVALID_QR_CODE`,
`OUTSIDE_CANTEEN_AREA`, `LOCATION_ACCURACY_TOO_LOW`, `LOCATION_STALE`, `LOCATION_INVALID`, `PRESENCE_NOT_CONFIGURED`.

## Tests

```bash
python -m pytest -v
```

- `tests/test_presence_geo.py` and `tests/test_presence_config.py` need no database.
- `tests/test_presence.py` covers the end-to-end rules: display and revocation access, valid and expired codes,
  replay, several students on one code, geofence, GPS accuracy and staleness, malformed input, unauthorized
  users, deactivated accounts, CSRF, direct order-API bypass, session expiry and reuse, transaction rollback,
  closed canteen, idempotent retry, retention, registration and static serving.
- Existing order tests use `tests/presence_helpers.py` to get a verified session. They test pricing and stock,
  not verification. `tests/test_presence.py` tests verification.

## Known gaps

- Concurrency is tested by sequential requests and enforced by database constraints. Parallel load testing is still needed.
- The 10-second rotation has a short changeover, so a code scanned at the exact moment it changes will fail. The student scans again.
- Checkout does not start the Razorpay payment flow. That was true before this change.
- The collection-QR scanner (`frontend/kitchen/js/scanner.js`) still has a demo fallback. It is outside this change.
