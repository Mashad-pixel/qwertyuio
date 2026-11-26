# Frontend API integration

| Endpoint | Method | Purpose | Authentication |
|---|---|---|---|
| `/api/auth/login` | POST | Staff or student login | None |
| `/api/auth/logout` | POST | End the current session | Session |
| `/api/auth/me` | GET | Current authenticated user | Session |
| `/api/orders` | POST | Create an order | Student login |
| `/api/orders` | GET | List the student's orders | Student login |
| `/api/orders/:id/tracking` | GET | Retrieve order tracking | Student login |
| `/api/payments/create-order` | POST | Create a Razorpay order | Session |
| `/api/payments/verify` | POST | Verify payment after checkout | Session |
| `/api/kitchen/orders` | GET | Retrieve the kitchen queue | Kitchen or admin |
| `/api/kitchen/orders/:id/status` | PATCH | Change an order status | Kitchen or admin |
| `/api/kitchen/collection/verify` | POST | Verify a collection token | Kitchen or admin |
| `/api/kitchen/collection/confirm` | POST | Confirm collection handover | Kitchen or admin |
| `/api/admin/orders` | GET | List orders for administration | Admin |

No menu or category API route is currently implemented in the inspected backend, so those interfaces intentionally show integration states instead of invented data.
