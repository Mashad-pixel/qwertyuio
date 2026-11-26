# Administrator panel

The administrator panel lives at `frontend/admin/` and talks only to the `/api` endpoints below. It keeps
no data in the browser and contains no sample data. Every figure, list and change comes from the server.

## 1. First-time setup

Run these from the project folder, with `.env` configured as in `.env.example`.

```bash
flask --app run db upgrade          # apply migrations (one head: f1a2b3c4d5e6)
flask --app run setup-admin         # create your administrator: prompts for email and password
flask --app run seed-menu           # optional: load the starter menu (creates its categories too)
flask --app run                     # or serve with gunicorn in production
```

`setup-admin` takes its password from a hidden prompt, typed twice. It is never read from an environment
variable, a script or the repository. It refuses to run once an administrator exists.

Then open `/frontend/admin/login.html`, sign in, and enrol an authenticator app. Administrators cannot use
any admin page until two-factor authentication is on.

### Operator commands (server console)

| Command | Use |
|---|---|
| `setup-admin [--name] --email` | Create the first administrator (refuses if one exists). |
| `reset-admin-credentials --current-email X [--new-email Y]` | Change an administrator's email and/or password when they cannot sign in. Ends their sessions. |
| `reset-mfa --email X` | Remove an account's authenticator (lost phone). It must enrol again. |
| `revoke-sessions --email X` | End every session for an account now. |
| `seed-menu` | Load `app/data/menu_seed.json` into an empty menu. |

## 2. Changing your own email or password

Settings → *Change sign-in email* and *Change password*. Both ask for your current password. Changing either
signs out every other session; this browser stays signed in. Settings also lists your active sessions and
lets you sign out the others.

## 3. Pages

| Page | What it does | APIs |
|---|---|---|
| Overview | Today and last 30 days: orders, paid, gross/net revenue, average order, revenue by day, top items, recent orders, ordering on/off | `/admin/reports/overview`, `/admin/reports/sales`, `/admin/reports/popular-items`, `/admin/orders`, `/canteen/status` |
| Orders | Filter by order and payment status, page through, open an order (items, totals, status history), cancel with a reason | `/admin/orders`, `/admin/orders/<id>`, `/admin/orders/<id>/cancel` |
| Menu | Search and filter, add and edit items, mark available/unavailable. Items must use an existing category | `/admin/menu`, `/admin/categories` |
| Categories | Add, rename (moves its items) and delete (only when empty) | `/admin/categories` |
| Reports | Today / 7 / 30 days or a custom range; revenue, refunds, items, categories, busiest hours, order statuses; CSV export | `/admin/reports/*` |
| Refunds | Refund a payment in full or in part with a reason; recent refunds and their provider status | `/admin/payments`, `/admin/payments/<id>/refund`, `/admin/payments/refunds` |
| Staff | Add administrator or kitchen accounts, change role, reset a password, activate or deactivate | `/admin/staff` |
| Settings | Canteen name and opening hours, pause/resume ordering with a message, account email/password, two-factor status, sessions | `/admin/canteen/settings`, `/admin/canteen/status`, `/account/*` |

## 4. Security model

- **Passwords** are stored only as salted scrypt hashes. The minimum is 8 characters with a letter and a number.
- **Administrator sign-in** needs the password and a time-based code (TOTP, replay-protected). Wrong codes lock the
  second step for a while. Administrators without two-factor set up get no admin access.
- **Sessions** are server-side rows. Admin sessions end after 30 minutes idle or 8 hours total (configurable).
  Logout ends the current session. A password or email change signs out every other session, a role change or
  deactivation ends that account's sessions, and the CLI reset commands end the account's sessions.
- **Login throttling**: 5 attempts per minute per IP, and 10 per 15 minutes per target email (hashed, so the
  limit follows the account, not the network).
- **Account changes** need the current password and are limited to 10 per 15 minutes per account.
- **CSRF**: every state-changing request needs the CSRF token (`api.js` sends it). Tests disable it for speed only.
- **Role checks** are server-side on every admin endpoint. Kitchen accounts get 403 on admin routes.
- **Content Security Policy** forbids inline scripts and inline event handlers on the admin pages. All server
  values are written as text, never as HTML.
- **CSV export** neutralises spreadsheet formulas (cells starting with `=`, `+`, `-`, `@`).
- No secrets are in the frontend, and no credentials are created by default.

## 5. Tests

```bash
python -m pytest                                              # full backend suite (needs requirements.txt)
python -m unittest tests.test_admin_panel_units tests.test_admin_panel_contract   # stdlib only
node --test tests/frontend/admin-panel.test.js                # frontend helpers, no npm install needed
```

- `test_admin_panel_units.py`: canteen detail rules, migration history (one head, no conflicting schema
  changes), and every `from app...` import resolving.
- `test_admin_panel_contract.py`: every admin API call matches a real route and method; admin HTML references
  existing files, has no inline script or handler, uses no browser storage, and has no placeholder text.
- `test_admin_panel.py`: setup and reset commands, account password/email/sessions, MFA gating, categories,
  canteen details, menu category rules, login throttle keys, seed categories.
- `test_authorization_matrix.py` has rows for every new route.

## 6. Known limits

- Orders cannot be searched by order number or phone; the list filters by status and payment only.
- Menu items cannot be deleted (only made unavailable), matching the existing backend.
- Email changes are confirmed with the current password only; there is no code sent to the new address.
- Rate-limit counters use process memory unless `RATELIMIT_STORAGE_URI` points at Redis. Configure Redis before
  running more than one worker.
- `app/services/account_recovery.py` is an abandoned draft that imports models which do not exist. Nothing
  imports it. It should be deleted; it was left in place because it is outside this change.
