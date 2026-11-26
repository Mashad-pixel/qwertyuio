# Pull request: Steps 5–7 (inventory, admin reports and refunds, final pass)

**Into:** `main`  **From:** `backend-operations`

## Summary

Completes the remaining backend steps for the trayUP canteen project:

- **Step 5 – Inventory:** tracked stock is held when an order is placed, sold when payment is confirmed, and released when the order expires or is cancelled. Stock updates are atomic, so two students can never both buy the last unit.
- **Step 6 – Admin reports and refunds:** admin cancellation, full and partial refunds confirmed by Razorpay, and sales reports.
- **Step 7 – Final pass:** full test suite, README update, and this description.

## What changed

**Stock and payment window**
- `menu_items.reserved_quantity` and a new `stock_reservations` table.
- Pricing checks available stock (stock minus held). Messages say how many are left, or that the item is sold out.
- Unpaid orders expire after `ORDER_PAYMENT_EXPIRY_MINUTES`, freeing their stock. Expiry runs before each new order and from the new `flask --app run expire-orders` command.
- Paying for an expired order returns `ORDER_EXPIRED`.

**Late payments (fixes a Step 2 gap)**
- Money captured after an order expired or was cancelled used to make the webhook fail with 500, so Razorpay retried it indefinitely.
- It is now recorded as `refund_required`, the order is not fulfilled, and the webhook returns 200.

**Admin cancellation**
- `POST /api/admin/orders/<id>/cancel`. Unpaid orders release their stock. Paid orders get their sold stock back and are flagged for refund. Collection codes stop working.

**Refunds**
- `POST /api/admin/payments/<id>/refund` (full or partial) and `GET /api/admin/payments/<id>/refunds`.
- Statuses change only after Razorpay confirms the refund, either in the response or by the `refund.processed` / `refund.failed` webhook.
- Refund webhooks can arrive before the refund row is saved. Those are retried (500) rather than dropped.

**Reports**
- `/api/admin/reports/{overview,sales,popular-items,categories,peak-hours,orders}`, admin only, grouped by canteen-local day.

**Fixes made while finishing the drafts**
- The draft `admin_orders.py` imported a `cancel_order` that didn't exist, which would stop the app from starting.
- The draft report queries joined `orders` to itself, which SQLAlchemy rejects.
- Category sales dropped revenue for items removed from the menu. They now appear under "Removed from menu".
- The draft refund webhook handling could drop a refund that arrived before it was saved (see above).
- Duplicate Razorpay client code and a duplicate outcome-constants module were merged into `razorpay_client.py` and `WebhookStatus`.

## Database migrations

Run `flask --app run db upgrade`. Two new revisions, applied in order:

1. `e7a1b2c3d4f5_add_stock_reservations` – `menu_items.reserved_quantity` (default 0, with check constraints) and `stock_reservations`.
2. `f2b3c4d5e6a7_add_refunds` – `refunds`.

No existing data needs changing. Existing menu items start with 0 held units.

## Configuration

- New: `CANTEEN_UTC_OFFSET_MINUTES` (default `330`, India). Add it to `.env`.
- Razorpay: add `refund.processed` and `refund.failed` to the webhook's events.
- Schedule `flask --app run expire-orders` every minute (cron or Task Scheduler).

## Review focus

Please review these first, since they carry the most risk:

1. `inventory_service.py`: every stock change is a conditional `UPDATE`. Check the WHERE clauses.
2. `payment_service._confirm_captured_payment`: the order of checks, and the commit-before-raise in the late-payment path.
3. `refund_service.py`: the webhook retry path for refunds that aren't saved yet.
4. `report_service.py`: the explicit `select_from` and outer joins.
5. `app/__init__.py`, `app/config.py`, `app/models/menu.py`: shared files, per the team notes in the README.

## Test status

- **Not yet run in CI.** Run `python -m pytest -v` locally before merging. Every test should pass.
- Added tests: `tests/test_inventory.py`, `tests/test_refunds.py`, `tests/test_reports.py`. Three extra tests were added: the refund webhook race, a late payment after admin cancellation, and the refund-required flag on cancelling a paid order.
- The existing tests were read against the new behavior. Behavior that changes on existing paths: (1) a late-payment webhook now returns 200 `processed` instead of failing with 500; (2) payment-failed webhooks are ignored for any payment that is no longer `created`, not only `paid`; (3) creating a payment for an expired order returns `ORDER_EXPIRED`; (4) order creation now holds stock and may return `INSUFFICIENT_STOCK` with a different message. No existing test asserted the old 500 result.

## Checklist

- [ ] `python -m pytest -v` passes locally
- [ ] `flask --app run db upgrade` succeeds on a fresh database
- [ ] `flask --app run expire-orders` prints the expected count
- [ ] `CANTEEN_UTC_OFFSET_MINUTES` set in `.env`
- [ ] Razorpay webhook events updated (`refund.processed`, `refund.failed`)
- [ ] Reviewed by Nehal (shared files)

## Known gaps (not in this PR)

Listed in the README under "Known Gaps". The main one is CSRF protection, which is planned as a separate change.
