# Fix notes

Before these fixes, `pytest` reported 34 failures. Now all 203 tests pass, `pyflakes` reports nothing,
and the migration chain builds a fresh database with no drift from the models.

## Bugs fixed in code

| File | Problem | Fix |
|---|---|---|
| `services/report_service.py` | `PAID_STATUSES` was used but never defined (`NameError` on every money report) | Constant restored |
| `services/razorpay_client.py` | Missing keys raised `RuntimeError`, so the API returned 500 | Raises `OrderError` (503 `PAYMENTS_NOT_CONFIGURED`) |
| `routes/payments.py` | `verify_checkout` was called with arguments in the wrong order, so every verify returned 404 | Arguments are now passed by name |
| `routes/payments.py` | `verify_checkout` returns a tuple, but the route treated it as an order | Route unpacks `(order, refund_required)`; a late payment returns 409 with the refund message |
| `services/payment_service.py` | `hmac.compare_digest` raises `TypeError` on non-ASCII signatures (500 instead of 400) | Non-ASCII input is rejected before comparing |
| `services/payment_service.py` | Missing webhook secret returned 400 instead of 503 | `WEBHOOKS_NOT_CONFIGURED` (503), same for checkout secret |
| `services/payment_service.py` | Webhook returned `True`/`False`, not the documented outcome | Returns `processed`, `ignored`, or `duplicate` |
| `services/refund_service.py` | Refund events with no refund ID were retried forever | Ignored (retrying can't help) |
| `routes/reports.py` | Report lists were returned as bare lists | Wrapped under `days`, `items`, `categories`, `hours` (the shape the tests and API docs use); peak-hours includes `timezone_offset_minutes` |
| `routes/auth.py` | Login clears the session, which also drops the CSRF token, so the next POST failed | Login and logout return a fresh `csrf_token` |

Unused imports were removed from several files.

## Test updates (the code was right, the tests were out of date)

- `test_orders.py`: error codes renamed to `MENU_ITEM_NOT_FOUND`, `QUANTITY_TOO_LARGE`, `INVALID_ITEMS`.
  Repeated menu items are now combined into one line (the documented design), not rejected.
- `test_payments.py`: bad Checkout signature returns `INVALID_SIGNATURE`; amount or owner mismatch returns 409 `PAYMENT_MISMATCH`.
- `test_refunds.py`: a refund webhook that arrives before its refund row is saved gets a 500 so Razorpay retries.
  The race test now checks the pending state before the retry. The unauthenticated test uses an anonymous client.
- `test_auth.py`: new test that login returns a CSRF token.

## Behavior decisions to confirm

1. **Captured payment for an unknown order** is now acknowledged (`ignored`, logged) instead of failing with 500.
   Otherwise Razorpay would retry it for about 24 hours with no way to fix it. Tell me if you want it to retry instead.
2. **Repeated menu items** are merged into one line, and the 20-unit limit applies to the combined quantity.
3. **Mismatch errors** return 409 (a conflict with the stored order), not 400.

## Setup after extracting

```powershell
pip install -r requirements.txt
flask --app run db upgrade
python -m pytest -v
```

Expected: `204 passed` (includes an end-to-end workflow test).
