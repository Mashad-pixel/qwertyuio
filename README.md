# TrayUP — Smart College Canteen
### QR-Based Online Ordering & Payment System with Real-Time Kitchen Integration

trayUP is a mobile-first web application for college canteens. Students scan a QR code to browse the menu, place food orders, pay online, and track preparation. Kitchen staff manage incoming paid orders and verify collection, while administrators manage menu items, staff, orders, and sales.

> **Project Status:** Development roadmap / planned implementation. Features described below should be treated as planned until they have been implemented and tested.

## Table of Contents

1. Project Overview
2. Problem Statement
3. Goals
4. User Roles
5. Main Workflows
6. Technology Stack
7. System Architecture
8. Project Structure
9. Database Design
10. Order and Payment Statuses
11. API Overview
12. Payment Integration
13. QR Code and Collection Security
14. Inventory and Failure Handling
15. Security Requirements
16. Real-Time Updates and Notifications
17. Local Development Setup
18. Environment Variables
19. Testing
20. Deployment Plan
21. Development Roadmap
22. Success Metrics
23. Future Enhancements

---

## 1. Project Overview

trayUP connects students, canteen kitchen staff, and administrators through one web application.

The system is designed to reduce physical queues, simplify digital ordering, provide clear order status updates, and maintain reliable digital records of orders and payments.

The application has three primary interfaces:

**Student Interface**
- QR-based menu access.
- Browse food items.
- Add items to cart.
- Checkout and online payment.
- Digital receipt.
- Real-time order tracking.

**Kitchen Interface**
- Secure staff login.
- View incoming paid orders.
- Manage food preparation.
- Update order status.
- Scan and verify collection QR codes.

**Admin Interface**
- Manage menu items and prices.
- Manage availability and inventory.
- Manage staff accounts.
- View and manage orders.
- Monitor payments and refunds.
- View sales reports and analytics.

## 2. Problem Statement

Traditional college canteens often face:

- Long queues during peak hours.
- Slow manual ordering and cash payments.
- No reliable way for students to check order progress.
- Confusion in the kitchen about items and quantities.
- Cash handling and reconciliation errors.
- Limited digital sales and inventory records.

trayUP aims to solve these problems through a centralized digital ordering and kitchen management system.

## 3. Goals

- Allow students to open the menu by scanning a QR code.
- Display current food prices and availability.
- Allow students to place orders without requiring an account in the first release.
- Calculate the final order amount securely on the backend.
- Accept online payments through Razorpay.
- Send only verified, captured paid orders to the kitchen.
- Provide student-facing order tracking.
- Generate digital receipts and secure collection QR codes.
- Prevent duplicate payment processing and duplicate collection.
- Give administrators control over menu items, staff, orders, and reports.

## 4. User Roles

### Student

- Scan the canteen QR code.
- Browse available food items.
- Add items and quantities to a cart.
- Enter name and phone number.
- Pay through Razorpay Checkout.
- View a receipt and track order status.
- Present the collection QR code when the order is ready.

### Kitchen Staff

- Log in using assigned credentials.
- View incoming paid orders.
- Review order items, quantities, instructions, and timestamps.
- Update preparation statuses.
- Scan and verify collection QR codes.
- Confirm food handover.

### Admin / Manager

- Manage menu items, categories, prices, and availability.
- Manage staff accounts and roles.
- View and search orders.
- Review payment and refund states.
- Configure canteen availability and operating settings.
- View sales and operational reports.

Public staff registration should not be enabled. Administrators should create staff accounts.

## 5. Main Workflows

### 5.1 Student Ordering Workflow

1. Student scans the printed canteen QR code.
2. The trayUP menu opens in the mobile browser.
3. Student browses available items.
4. Student adds items and quantities to the cart.
5. Student enters basic customer details.
6. Backend validates item IDs and quantities.
7. Backend retrieves current prices from the database.
8. Backend calculates the total in paise.
9. Backend creates an internal order and item-price snapshots.
10. Backend creates a Razorpay order for the server-calculated amount.
11. Student completes payment through Razorpay Checkout.
12. Backend verifies the payment response and confirms captured payment.
13. The paid order becomes available to the kitchen.
14. Student tracks the order.
15. Student presents the collection QR when the order is ready.
16. Kitchen staff verify and confirm the handover.

### 5.2 Kitchen Workflow

1. Staff logs in.
2. New paid orders appear in the kitchen dashboard.
3. Staff reviews items, quantities, and instructions.
4. Staff changes the order to PREPARING.
5. Staff changes it to READY when preparation is complete.
6. Student presents the collection QR.
7. Staff scans the QR.
8. Backend verifies payment, order status, token validity, and unused state.
9. Staff confirms the handover.
10. Backend marks the order COLLECTED and invalidates the collection token.

### 5.3 Admin Workflow

1. Admin logs in.
2. Admin creates and updates menu items.
3. Admin controls item availability and stock.
4. Admin creates or disables staff accounts.
5. Admin reviews orders and payment states.
6. Admin handles cancellation and refund workflows.
7. Admin reviews sales and operational reports.

## 6. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | HTML, CSS, JavaScript | Responsive interfaces |
| Backend | Python, Flask | Application server and REST APIs |
| ORM | Flask-SQLAlchemy | Database access |
| Migrations | Flask-Migrate | Database schema changes |
| Development Database | SQLite | Local development |
| Production Database | PostgreSQL | Persistent production records |
| Payments | Razorpay | Online payment processing |
| QR Generation | Python qrcode | QR code generation |
| Authentication | Flask sessions / Flask-Login | Staff authentication |
| CSRF Protection | Flask-WTF | Request protection |
| Rate Limiting | Flask-Limiter | API protection |
| Testing | pytest | Automated testing |
| Production Server | Gunicorn | Application serving |

### Initial Implementation Choices

- Use guest checkout for students in the first release.
- Use secure sessions and role-based authorization for staff.
- Use short-interval polling for order updates initially.
- Consider WebSockets after the core workflow is stable.
- Keep frontend and backend in one Flask application for the first release.

## 7. System Architecture

```text
                   STUDENT MOBILE BROWSER
                QR → Menu → Cart → Checkout
                              |
                              v
                     FLASK APPLICATION
           ---------------------------------------
           | Orders | Pricing | Payments         |
           | Auth   | Kitchen | Collection QR    |
           | Admin  | Reports | Inventory        |
           ---------------------------------------
                    |                 |
                    v                 v
               DATABASE           RAZORPAY
          Users, Menu, Orders,   Checkout, Payment
          Payments, Events,      Verification,
          Tokens, Audit Logs     Webhooks, Refunds
                    |
          -----------------------
          |                     |
          v                     v
    KITCHEN DASHBOARD      ADMIN DASHBOARD
    Paid order queue       Menu and staff
    Preparation            Orders and reports
    Collection             Payment/refund review
```

The frontend must not connect directly to the database. The Razorpay secret must remain on the backend and must never be sent to the browser.

## 8. Project Structure

```text
trayUP/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── extensions.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── menu.py
│   │   ├── order.py
│   │   ├── order_item.py
│   │   ├── payment.py
│   │   ├── webhook.py
│   │   ├── collection_token.py
│   │   └── order_status_history.py
│   ├── routes/
│   │   ├── public.py
│   │   ├── orders.py
│   │   ├── payments.py
│   │   ├── webhooks.py
│   │   ├── auth.py
│   │   ├── kitchen.py
│   │   └── admin.py
│   ├── services/
│   │   ├── pricing_service.py
│   │   ├── order_service.py
│   │   ├── payment_service.py
│   │   ├── inventory_service.py
│   │   ├── collection_service.py
│   │   └── report_service.py
│   ├── security/
│   │   ├── permissions.py
│   │   ├── authentication.py
│   │   └── validation.py
│   ├── templates/
│   │   ├── student/
│   │   ├── kitchen/
│   │   ├── admin/
│   │   └── errors/
│   └── static/
│       ├── css/
│       ├── js/
│       └── images/
├── migrations/
├── tests/
├── instance/
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py
├── wsgi.py
└── README.md
```

This is the recommended structure and can be adjusted to match the actual implementation.

## 9. Database Design

All relationships should use foreign keys and appropriate database constraints. Use database transactions for operations that update multiple related records.

### 9.1 Users

Stores staff and administrator accounts.

| Column | Description |
|---|---|
| id | Primary key |
| name | Staff name |
| email | Unique login email |
| password_hash | Secure password hash |
| role | ADMIN or KITCHEN |
| is_active | Account status |
| created_at | Creation timestamp |

### 9.2 Menu_Items

| Column | Description |
|---|---|
| id | Primary key |
| name | Food item name |
| description | Item description |
| category | Menu category |
| price_paise | Price in paise |
| image_url | Item image |
| is_available | Current availability |
| stock_quantity | Optional stock count |
| created_at | Creation timestamp |
| updated_at | Last update timestamp |

Use integer paise values instead of floating-point values for monetary calculations.

### 9.3 Orders

| Column | Description |
|---|---|
| id | Internal UUID |
| order_code | Human-readable unique order code |
| customer_name | Student name |
| customer_phone | Student contact number |
| tracking_token_hash | Hash of private tracking token |
| total_paise | Server-calculated order amount |
| order_status | Fulfilment status |
| payment_status | Financial status |
| special_instructions | Optional instructions |
| created_at | Order creation timestamp |
| updated_at | Last update timestamp |
| ready_at | Time order became ready |
| collected_at | Time order was collected |

### 9.4 Order_Items

Stores the items belonging to an order.

| Column | Description |
|---|---|
| id | Primary key |
| order_id | Foreign key to Orders |
| menu_item_id | Foreign key to Menu_Items |
| item_name_snapshot | Name at purchase time |
| unit_price_paise | Price at purchase time |
| quantity | Ordered quantity |
| line_total_paise | Quantity multiplied by unit price |

Snapshots preserve historical receipts when menu names or prices change.

### 9.5 Payments

An order can have multiple payment attempts. Store each attempt separately.

| Column | Description |
|---|---|
| id | Primary key |
| order_id | Related internal order |
| gateway | Payment provider |
| gateway_order_id | Razorpay order ID |
| gateway_payment_id | Razorpay payment ID |
| amount_paise | Expected payment amount |
| currency | Normally INR |
| status | Payment attempt state |
| signature_verified_at | Verification timestamp |
| captured_at | Capture timestamp |
| refund_id | Gateway refund ID |
| created_at | Creation timestamp |

### 9.6 Webhook_Events

| Column | Description |
|---|---|
| id | Primary key |
| gateway_event_id | Unique Razorpay event ID |
| event_type | Event name |
| payload_hash | Hash for event audit |
| processing_status | Processing result |
| received_at | Receipt timestamp |
| processed_at | Processing timestamp |

The unique event ID helps prevent duplicate webhook processing.

### 9.7 Collection_Tokens

| Column | Description |
|---|---|
| id | Primary key |
| order_id | Related order |
| token_hash | Hash of random collection token |
| issued_at | Issue timestamp |
| expires_at | Expiry timestamp |
| used_at | Consumption timestamp |

### 9.8 Order_Status_History

Stores each status transition, including the previous status, new status, staff account, and timestamp.

## 10. Order and Payment Statuses

Order fulfilment and payment must be tracked independently.

### Order Status

| Status | Meaning |
|---|---|
| PENDING_PAYMENT | Waiting for successful payment confirmation |
| RECEIVED | Payment captured; order accepted for kitchen processing |
| PREPARING | Kitchen is preparing the order |
| READY | Order is ready for collection |
| COLLECTED | Food has been handed over |
| CANCELLED | Order will not be fulfilled |

### Payment Status

| Status | Meaning |
|---|---|
| UNPAID | No captured payment |
| PAID | Payment captured and confirmed |
| REFUND_PENDING | Refund request initiated |
| REFUNDED | Refund confirmed |

Individual payment attempts should additionally record gateway states such as CREATED, AUTHORIZED, CAPTURED, and FAILED.

Never mark an order as paid merely because the browser reports a successful Checkout callback. Confirm the payment through trusted backend verification and gateway state.

## 11. API Overview

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| GET | /api/menu | Public | List available menu items |
| GET | /api/canteen/status | Public | Get canteen ordering status |
| POST | /api/orders | Public | Create an order |
| GET | /api/orders/{id} | Tracking token | Get order details and status |
| POST | /api/orders/{id}/payment-order | Order owner | Create Razorpay order |
| POST | /api/payments/verify | Payment flow | Verify Checkout response |
| POST | /api/payments/webhook | Razorpay | Receive gateway events |
| POST | /api/auth/login | Staff | Staff login |
| POST | /api/auth/logout | Staff | Staff logout |
| GET | /api/staff/orders | Kitchen/Admin | Fetch active kitchen orders |
| PATCH | /api/staff/orders/{id}/status | Kitchen/Admin | Update preparation status |
| POST | /api/staff/collection/preview | Kitchen/Admin | Validate scanned token |
| POST | /api/staff/collection/confirm | Kitchen/Admin | Confirm handover |
| GET | /api/admin/menu | Admin | List all menu items |
| POST | /api/admin/menu | Admin | Create menu item |
| PATCH | /api/admin/menu/{id} | Admin | Update menu item |
| GET | /api/admin/orders | Admin | Search and view orders |
| GET | /api/admin/reports | Admin | View reports |
| POST | /api/admin/staff | Admin | Create staff account |
| PATCH | /api/admin/staff/{id} | Admin | Update or disable staff account |

Student order tracking must require a private token or another appropriate ownership mechanism. A guessable order ID must not grant access to personal order information.

## 12. Payment Integration

### 12.1 Payment Provider

trayUP is planned to use Razorpay Standard Checkout.

Use Razorpay Test Mode during development. Test transactions do not transfer real money.

Live payments require appropriate merchant onboarding, verification, activation, and settlement configuration. The canteen or authorized institution should own or explicitly authorize the merchant account and settlement arrangement.

Do not assume that a payment gateway is permanently free. Check current Razorpay pricing, offer eligibility, applicable taxes, payment-method exclusions, and account-specific terms before going live.

Official references:

- [Razorpay Documentation](https://razorpay.com/docs/)
- [Razorpay Orders API](https://razorpay.com/docs/api/orders/)
- [Payment Signature Verification](https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/validate-signature/)
- [Razorpay Webhooks](https://razorpay.com/docs/webhooks/)
- [Razorpay Pricing](https://razorpay.com/pricing/)

### 12.2 Secure Payment Creation

The frontend sends item IDs and quantities to the backend. It must not determine the payment amount.

The backend:

1. Retrieves the internal order.
2. Validates the trusted stored amount.
3. Creates a Razorpay order in INR.
4. Sends the amount as integer paise.
5. Stores the Razorpay order ID against the correct internal payment attempt.
6. Returns only the public Checkout information required by the browser.

Example:

```python
amount_paise = 13000  # ₹130.00

razorpay_order = client.order.create({
    "amount": amount_paise,
    "currency": "INR",
    "receipt": order.order_code
})
```

### 12.3 Signature Verification

After Checkout, the backend must verify the payment signature using the expected Razorpay order ID, payment ID, and secret key.

The backend must also ensure that:

- The payment belongs to the correct internal order.
- The expected amount matches.
- The currency matches.
- The payment is actually captured before kitchen fulfilment.

Never expose the Razorpay Key Secret in frontend JavaScript, HTML, or public repositories.

### 12.4 Webhook Processing

The webhook endpoint must:

- Validate the webhook signature against the raw request body.
- Use the configured webhook secret.
- Record the unique event ID.
- Process each event idempotently.
- Handle duplicate and out-of-order events.
- Verify that the payment maps to the expected internal order and amount.
- Avoid allowing stale events to reverse a confirmed captured payment.

The webhook is important when the student closes the browser or loses connectivity after completing payment.

### 12.5 Refunds

If an order cannot be fulfilled after payment:

1. Record the cancellation reason.
2. Prevent kitchen fulfilment.
3. Initiate the refund through the gateway.
4. Store the refund identifier.
5. Track the refund state.
6. Mark the payment REFUNDED only after confirmation.

## 13. QR Code and Collection Security

There are two distinct QR use cases.

### Canteen Entry QR

A static QR code opens the public menu:

```text
https://your-domain.example/menu
```

It does not contain payment details, student information, or private secrets.

### Order Collection QR

A separate random, high-entropy token is generated for an order. Store only its hash in the database and display the raw token in the student's private order page.

The backend must verify:

- The token exists.
- The token has not expired.
- The token has not already been used.
- The related order is paid.
- The related order is READY.
- The token belongs to that order.

After staff confirm the handover, consume the token and mark the order COLLECTED in one database transaction. A second collection attempt must fail.

Scanning alone should not automatically mark an order as collected. Staff should review the order and explicitly confirm handover.

## 14. Inventory and Failure Handling

Start with item-level availability and optional stock quantities.

For stock-controlled items:

1. Check stock when the order is created.
2. Reserve the required quantity using a database transaction.
3. Apply a defined payment expiry window.
4. Convert the reservation into a sale after confirmed payment.
5. Release the reservation after a definitive failed or expired payment.
6. Reconcile ambiguous payment outcomes before releasing stock.

Do not release stock simply because the browser closed or a Checkout callback was missed. A delayed webhook may still confirm payment.

For simultaneous orders, use database transactions and appropriate row locking or atomic conditional updates so stock cannot become negative.

Ingredient-level inventory can be added later.

## 15. Security Requirements

- Use HTTPS in production.
- Store secrets in environment variables or the hosting provider's secret manager.
- Keep .env out of version control.
- Hash staff passwords using a secure password-hashing algorithm.
- Use secure session cookies.
- Enable CSRF protection for session-authenticated state-changing requests.
- Apply rate limits to login, order creation, payment, and token verification endpoints.
- Enforce role-based authorization on every staff and admin endpoint.
- Never trust frontend prices, totals, roles, or payment status.
- Validate all input on the backend.
- Use ORM parameterization and database constraints.
- Verify Razorpay Checkout signatures and webhook signatures.
- Process webhooks idempotently.
- Use unpredictable, expiring, one-time collection tokens.
- Prevent duplicate collection with atomic state transitions.
- Avoid exposing personal information through public order identifiers.
- Limit uploaded file types and sizes.
- Keep audit records for staff actions and important order transitions.
- Do not log passwords, secrets, or unnecessary sensitive payment data.
- Back up the production database and test restoration.

## 16. Real-Time Updates and Notifications

### Initial Release

Use short-interval polling, approximately every 3–5 seconds, for:

- Kitchen order queue updates.
- Student order status updates.

Polling is simpler to deploy and maintain for an initial prototype.

### Later Enhancement

Add WebSockets when needed to push:

- New paid orders to the kitchen.
- Preparation status changes to students.
- Ready-for-collection notifications.

Start with in-website updates. Push notifications, SMS, and email can be added later if their service costs and operational requirements are acceptable.

## 17. Local Development Setup

### Requirements

- Python 3.10 or newer.
- Git.
- A code editor.
- A Razorpay account for Test Mode credentials.

### 17.1 Clone the Repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd trayUP
```

### 17.2 Create a Virtual Environment

Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 17.3 Install Dependencies

```bash
pip install -r requirements.txt
```

### 17.4 Configure Environment Variables

Copy .env.example to .env and fill in the local values.

Do not commit .env to Git.

### 17.5 Initialize the Database

If Flask-Migrate is configured:

```bash
flask db upgrade
```

Use the project's documented CLI command to create the first administrator account. Do not add a public admin-registration route.

### 17.6 Run the Development Server

```bash
python run.py
```

Open the local address printed by Flask, commonly:

```text
http://127.0.0.1:5000
```

The exact commands may need adjustment to match the application's Flask configuration and entry point.

## 18. Environment Variables

Example .env.example:

```dotenv
FLASK_ENV=development
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URL=sqlite:///canteen.db

RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=

ORDER_PAYMENT_EXPIRY_MINUTES=10
COLLECTION_TOKEN_EXPIRY_MINUTES=60

PUBLIC_BASE_URL=http://127.0.0.1:5000
```

Notes:

- Use a strong, randomly generated SECRET_KEY.
- Keep Razorpay credentials empty until configured.
- Use Test Mode keys for development.
- Use separate Live Mode credentials for production.
- Never commit real secrets to GitHub.
- Use PostgreSQL's connection URL for production.
- Configure production cookie security and HTTPS settings separately.

## 19. Testing

Use pytest for backend tests and browser-based testing for the user interfaces.

### Student Ordering Tests

- Menu loads correctly.
- Available items can be added to the cart.
- Quantities update correctly.
- Unavailable items cannot be ordered.
- Invalid quantities are rejected.
- Frontend price manipulation does not change the backend total.
- Duplicate order submissions are handled safely.

### Payment Tests

- Successful Test Mode payment.
- Failed payment.
- Invalid Checkout signature.
- Incorrect amount.
- Incorrect currency.
- Payment mapped to the wrong order.
- Duplicate webhook delivery.
- Out-of-order webhook delivery.
- Browser closes after payment.
- Refund initiation and confirmation.

### Kitchen Tests

- Staff login and logout.
- Inactive staff cannot log in.
- Unauthorized users cannot access kitchen routes.
- Only paid orders enter the kitchen queue.
- Invalid status transitions are rejected.
- Status changes are recorded in history.

### Collection Tests

- Valid collection QR.
- Invalid token.
- Expired token.
- Reused token.
- Token belonging to another order.
- Unpaid order cannot be collected.
- Non-ready order cannot be collected.
- Concurrent collection attempts cannot collect the same order twice.

### Admin Tests

- Menu creation and updates.
- Availability changes.
- Staff creation and disabling.
- Order search.
- Sales calculations.
- Refund reporting.
- Role restrictions.

### Device and Network Testing

Test on Android, iOS, tablet, and desktop browsers. Test slow connections, lost connectivity, repeated taps, page refreshes, and browser closure during checkout.

## 20. Deployment Plan

### Before Deployment

- Use PostgreSQL for production.
- Apply database migrations.
- Configure HTTPS.
- Configure production environment variables.
- Set secure session-cookie options.
- Configure Razorpay Live Mode only after merchant activation and authorization.
- Register and verify the production webhook URL.
- Create administrator and kitchen accounts.
- Add the actual canteen menu and prices.
- Test order, payment, kitchen, and collection flows.
- Configure database backups and logging.

### Zero-Budget Development Approach

| Component | Initial Approach |
|---|---|
| Coding and testing | Local machine |
| Frontend | Served by Flask |
| Backend | Flask |
| Local database | SQLite |
| Payment development | Razorpay Test Mode |
| QR generation | Local Python library |
| Notifications | In-app updates |
| Order updates | Polling |
| Public demo | Free hosting tier, if suitable |

Free hosting plans may have sleep limits, storage limits, request limits, or non-persistent filesystems. Do not assume a free plan is suitable for real transactional canteen operations. Verify the provider's current terms and use persistent production storage.

## 21. Development Roadmap

Build in this order so later modules depend on stable earlier modules.

| Phase | Work | Completion Condition |
|---|---|---|
| 1 | Flask foundation and database | Application starts and migrations work |
| 2 | Database models and admin menu | Admin can manage menu and availability |
| 3 | Student menu and cart | Student can build an order on mobile |
| 4 | Order and pricing engine | Backend calculates trusted totals |
| 5 | Razorpay integration | Captured payment is verified and recorded |
| 6 | Kitchen dashboard | Paid orders appear and statuses update |
| 7 | Tracking and collection QR | Valid orders can be collected exactly once |
| 8 | Inventory and reports | Stock and sales records are consistent |
| 9 | Security and testing | Critical workflow and abuse tests pass |
| 10 | Deployment and pilot | Production setup is verified with canteen staff |

### First-Release Scope

Prioritize:

- QR-based menu access.
- Menu and availability management.
- Guest ordering.
- Server-side pricing.
- Razorpay Test Mode integration.
- Payment verification and webhooks.
- Kitchen order queue.
- Student order tracking.
- Collection QR verification.
- Basic admin reports.
- Security and automated tests.

Defer student accounts, loyalty points, coupons, college ID integration, multi-canteen support, advanced inventory, AI recommendations, and native mobile applications.

## 22. Success Metrics

Track these metrics after the pilot:

- Orders per day.
- Average order value.
- Payment success rate.
- Average preparation time.
- Order completion rate.
- Cancellation and refund rate.
- Average kitchen processing time.
- Peak ordering periods.
- Most frequently ordered items.
- Student feedback and repeat order rate.

A payment success target above 95% and an average preparation target below 10 minutes can be used as initial goals, but actual performance depends on the canteen, payment methods, menu, and operating conditions.

## 23. Future Enhancements

Possible improvements after the first release:

- Student accounts and order history.
- College ID integration.
- Scheduled pre-orders and pickup time slots.
- Loyalty points and discounts.
- Feedback and ratings.
- Ingredient-level inventory.
- Multiple canteen support.
- Multi-language interface.
- Advanced analytics.
- Push notifications.
- WebSocket-based live updates.
- Offline-friendly menu access.

Only add enhancements after the core order-to-payment-to-collection workflow is reliable.
-------------------------


## Integrated Part 1 foundation endpoints

The backend now exposes the compatible foundation endpoints alongside the order, payment,
kitchen, collection, refund, and reporting workflows:

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| GET | `/api/health` | Public | Database health check |
| GET | `/api/csrf-token` | Public | Obtain the token required on state-changing browser requests |
| GET | `/api/menu` | Public | Return available, in-stock menu items without internal stock counters |
| GET | `/api/canteen/status` | Public | Read the canteen's order-acceptance state |
| GET | `/api/admin/menu` | Admin | View menu items, stock and reservations |
| POST | `/api/admin/menu` | Admin | Create a menu item |
| PATCH | `/api/admin/menu/<id>` | Admin | Update menu details and availability |
| PATCH | `/api/admin/canteen/status` | Admin | Open or close ordering |

Browser clients must fetch `/api/csrf-token` and send the returned value in the
`X-CSRFToken` header for POST, PATCH, and DELETE requests. The Razorpay webhook is
exempt from browser CSRF checks and remains protected by Razorpay signature verification.

The canteen defaults to open until an administrator closes it. New order creation is rejected
with `CANTEEN_CLOSED` while closed. Reopening the canteen allows new orders again.

The uploaded Part 1 package used a different UUID-based guest-order schema. Its order,
collection-token, authentication and migration files were not copied over the current app,
because the existing payments, refunds and kitchen workflows depend on the repository's
integer order IDs and student ownership model. Guest checkout remains a separate integration
task; this commit preserves the currently working authenticated-order/payment architecture.

## Deployment (Render backend + Vercel frontend)

The Flask application and its SQL database run on Render. The static frontend is deployed separately to Vercel and calls the backend through the Vercel `/api/*` rewrite, so browser requests remain same-origin.

### Render

1. In Render, choose **New → Blueprint** and connect this repository, `Mashad-pixel/TrayUP`, branch `main`.
2. Render reads `render.yaml` from the repository root and creates the Flask web service and PostgreSQL database.
3. Open the web service's **Environment** settings and add the Razorpay secrets:
   - `RAZORPAY_KEY_ID`
   - `RAZORPAY_KEY_SECRET`
   - `RAZORPAY_WEBHOOK_SECRET`
4. Under **Secret Files**, upload your newly generated Firebase service-account JSON as `serviceAccountKey.json`. The blueprint expects it at `/etc/secrets/serviceAccountKey.json`. Never commit this file.
5. Wait for the deploy to finish, then check `https://YOUR-RENDER-SERVICE.onrender.com/api/health`.
6. Create the first admin using the project's Flask CLI command documented in the Administration section below (or run `flask --app wsgi:app create-user ...` in the Render Shell if that command is available in the deployed version).

**Database note:** the included Blueprint uses Render's free PostgreSQL plan for a demo deployment. Free Render databases are temporary and expire according to Render's current free-database policy. Do not use this database for permanent canteen orders or real payments. For production, change the database plan in `render.yaml` to a currently available paid persistent plan before deploying.

### Vercel

1. In Vercel, choose **Add New → Project** and import `Mashad-pixel/TrayUP`.
2. Set **Root Directory** to `frontend`.
3. Deploy the project. Vercel serves the static HTML/CSS/JavaScript from this folder.
4. The file `frontend/vercel.json` proxies `/api/*` to `https://trayup-mashad-api.onrender.com/api/*`. If Render assigns a different service hostname, update the destination in `frontend/vercel.json` to the exact Render URL and redeploy Vercel.

### Required post-deployment checks

- Confirm the Render `/api/health` endpoint reports both application and database healthy.
- In Vercel, test student menu loading, login/logout, admin and kitchen access, checkout, Razorpay test payment, webhook verification, and order status updates.
- In Firebase Console, verify that only the intended minimal order mirror is written.
- Configure the Razorpay webhook URL to the Render service's payment webhook endpoint shown by the application; use HTTPS and the exact route implemented in the payment routes.
- Keep the Firebase service-account key, Flask secret, and Razorpay secrets only in Render environment/secret-file settings, never in GitHub or Vercel.

