# Changes

1. **Checkout idempotency key persists across refresh** (`frontend/student/js/checkout.js`).
   The key is stored in sessionStorage, tied to the cart contents, so a retry after a refresh or a
   dropped response reuses it and the server returns the original order. It is cleared when the
   order is completed or can no longer be paid.
2. **Confirmation page closing tag fixed** (`frontend/student/confirmation.html`): `</bod</html>` is now `</body></html>`.
3. **Order tracking pages through all orders** (`frontend/student/js/tracking.js`): 10 orders per page
   with a "Load more orders" button, replacing the single `per_page=50` request. A failed load-more
   keeps the orders already shown.
4. **Admin reports use the real reporting API** (`frontend/admin/js/reports.js`): overview, sales by day,
   top items, categories and busiest hours come from `/api/admin/reports/*` for the chosen date range.
   The hardcoded sample figures and the fake CSV export were removed; the CSV is built from the loaded data.
5. **Admin menu uses the real menu API** (`frontend/admin/js/menu.js`): lists items from `/api/admin/menu`,
   and adds, edits and enables/disables items through the existing endpoints. The localStorage demo data
   was removed. The backend has no delete endpoint, so there is no delete action.
6. **Staff page no longer shows fake data** (`frontend/admin/staff.html`, `js/staff.js` removed): this
   version of the backend has no staff API, so the page states that plainly.
7. **Outdated admin placeholder text removed** from `menu.html` and `reports.html`.

## Round 2

8. **Password recovery and backup codes** (item 6). New endpoints under `/api/forgot/*`,
   `/api/recovery/*` and `/api/auth/recovery-codes`, matching the login page's recovery screens.
   - Email code: 6 digits, expires after 5 minutes, locks after 5 wrong tries, single use. Resend
     is limited to one every 30 seconds and five per hour. Only an HMAC of the code is stored.
   - Verifying the code returns a reset token that works once and expires after 10 minutes.
   - Replies never reveal whether an email has an account.
   - A password reset signs out every session (sessions record when they were authenticated).
   - Backup codes: eight single-use codes, shown once, stored hashed. Generating new codes
     replaces the unused ones.
   - Support requests are stored with a reference number for staff review (`GET
     /api/admin/recovery-requests`). Nothing is approved automatically.
   - Delivery: SMTP, configured through `RECOVERY_DELIVERY` and `SMTP_*`. Development can log
     codes with `console`. Production refuses `console` and `memory`, so codes are never written
     to logs there. Recovery by mobile number is not available yet, because accounts have no phone field.
   - The login page now sends requests through the shared API client. It had been posting without
     a CSRF token and displaying the error object instead of its message.
9. **Checkout details sent and stored** (item 7). The order request carries the customer name,
   phone and special instructions. They are validated on the server (phone as a 10-digit Indian
   mobile, stored as `+91…`; name up to 100 characters; instructions up to 500) and returned with
   the order.
10. **Idempotency keys tied to the request** (item 8). Each order stores a fingerprint of its
    items and customer details. Reusing a key for a different request returns `409
    IDEMPOTENCY_KEY_REUSED` and changes nothing. Orders created before this change are compared by
    items only, because their details were never recorded. Checkout drops the saved key when it
    receives that error.

Migration: `migrations/versions/3f9a1c2b4d5e_add_recovery_and_order_details.py` (run `flask db upgrade`).
