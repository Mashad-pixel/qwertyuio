# trayUP — Part 1 setup

Part 1 creates the Flask foundation, database extensions, account model, session authentication, staff-account CLI, and a minimal authenticated order endpoint for the first integration tests.

## Install

Python 3.10+ is recommended.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Set a long, random `SECRET_KEY` in `.env` before using the app beyond local development.

## Initialize the database

Run once after installing dependencies:

```bash
flask --app run.py db init
flask --app run.py db migrate -m "Initial trayUP schema"
flask --app run.py db upgrade
```

After changing models, generate and apply a new migration:

```bash
flask --app run.py db migrate -m "Describe schema change"
flask --app run.py db upgrade
```

## Create a staff account

Public staff registration is intentionally disabled. Create accounts from a trusted terminal:

```bash
flask --app run.py create-user --name "Canteen Admin" --email admin@example.com --role ADMIN
```

The command securely prompts for the password twice. Supported roles: `ADMIN`, `KITCHEN`, and `STUDENT`. Administrators set up two-factor authentication at their first sign-in.

## Run the app

```bash
python run.py
```

Open http://127.0.0.1:5000.

## Authentication endpoints

- `POST /api/auth/login` — JSON body with `email` and `password`; limited to five attempts per minute per client IP.
- `POST /api/auth/logout` — logs out and clears the session.
- `GET /api/auth/me` — returns the current session user's public profile.
- `GET /api/auth/csrf` — returns a CSRF token for browser clients.

For browser session requests, fetch `/api/auth/csrf` first, then include the returned token as `X-CSRFToken` on every state-changing request. Keep the session cookie. Automated tests disable CSRF checks to isolate API behavior; normal development and production enable them.

Example login:

```json
{"email": "admin@example.com", "password": "your-password"}
```

A browser-supplied user ID is never used to establish identity. Protected endpoints use the user loaded by Flask-Login from the signed session.

## Initial order endpoint

`POST /api/orders` requires login. The request contains menu item IDs and quantities; the backend loads prices from the database and calculates totals in integer paise. Supply an `Idempotency-Key` header to safely retry a request.

```json
{"items": [{"menu_item_id": 1, "quantity": 2}]}
```

Payment processing, guest checkout, kitchen workflows, inventory reservation, and collection QR verification are later parts and are not implemented here.

## Tests

```bash
pytest
```

Tests use isolated in-memory SQLite and cover login, sessions, disabled users, credential errors, logout, and authenticated order creation.

## Load the starter menu

The menu lives in the database and is edited from the admin Menu page. A new database starts empty. To load the 43 starter dishes once, run:

```bash
flask --app wsgi:app seed-menu
```

The command does nothing if the menu already has items, so it is safe to run on every deploy. Every entry goes through the same validation as the admin page.

## Administrator sign-in and recovery

Administrator accounts must use two-factor authentication (an authenticator app such as Google Authenticator or Aegis). The first time an administrator signs in, the sign-in page shows a setup key. They add it to the app and enter the 6-digit code to finish. Until then the account can reach only the sign-in and enrollment endpoints.

If an administrator loses their phone, a server operator resets the second factor and ends that account's sessions:

```bash
flask --app wsgi:app reset-mfa --email admin@example.com
```

To end all of an account's sessions without changing its second factor, run `flask --app wsgi:app revoke-sessions --email <address>`. Run `flask --app wsgi:app prune-sessions` on a schedule to delete finished session records.

Privileged sessions end after 30 minutes idle or 8 hours total. Student sessions end after 12 hours idle or 7 days total. These limits are set with `SESSION_*` environment variables.

## Production checklist

- Set `FLASK_CONFIG=production` and a strong `SECRET_KEY` (at least 32 characters). The app refuses to start otherwise.
- Use PostgreSQL and persistent storage.
- Set `SESSION_COOKIE_SECURE=true` behind HTTPS. Production enforces this.
- Set `RATELIMIT_STORAGE_URI` to a shared Redis instance (`redis://` or `rediss://`). The app refuses to start with `memory://` in production. `render.yaml` provisions one.
- Set `MENU_IMAGE_ALLOWED_HOSTS` to the exact image hosts you use. Menu images must be `https://` on one of these hosts, or a `/static/` path.
- Set `CSP_REPORT_ONLY=true` to watch for policy violations before enforcing. Production enforces the policy by default.
- Apply migrations during deployment.
- Keep all secrets out of Git. The `secret-scan` workflow checks every branch, tag and pull request.
