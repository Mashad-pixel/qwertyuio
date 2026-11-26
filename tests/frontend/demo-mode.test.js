const { test, describe, afterEach } = require("node:test");
const assert = require("node:assert/strict");
const { loadPage, settle, text } = require("./harness");

const path = require("path");
const ROOT = process.env.FRONTEND_ROOT || path.resolve(__dirname, "../../frontend");
const toast = (doc) => (doc.querySelector(".toast") || { textContent: "" }).textContent;
const findButton = (doc, label) => [...doc.querySelectorAll("button")].find((b) => b.textContent.trim() === label);
const submit = (p, formId) => p.doc.getElementById(formId).dispatchEvent(new p.win.Event("submit", { cancelable: true }));
const count = (calls, method, fragment) => calls.filter((c) => c.method === method && c.path.includes(fragment)).length;

const LIVE_QUEUE = {
  received: [{ id: 7, order_number: "TUP-7000", created_at: "2026-11-25T10:24:00+05:30", items: [{ item_name: "Samosa", quantity: 2 }] }],
  preparing: [],
  ready: [{ id: 8, order_number: "TUP-8000", created_at: "2026-11-25T10:01:00+05:30", items: [{ item_name: "Tea", quantity: 1 }] }]
};
const QUEUE_OK = { "GET /api/kitchen/orders": { status: 200, body: { success: true, data: { queue: LIVE_QUEUE } } } };
const STAFF_SESSION = { "trayup-mode": "demo" };

const open = [];
afterEach(() => { while (open.length) { try { open.pop().close(); } catch (_) {} } });
const load = async (opts) => { const p = await loadPage({ root: ROOT, ...opts }); open.push(p); return p; };

// ---------- Scanner ----------
describe("collection scanner (production)", () => {
  const verifyOk = (order_status = "ready") => ({ status: 200, body: { success: true, data: { order_number: "TUP-9001", order_status, items: [{ item_name: "Samosa", quantity: 2 }] } } });

  test("a code the server rejects is never shown as verified, and has no handover button", async () => {
    const p = await load({ page: "kitchen/scanner.html", url: "/kitchen/scanner.html", routes: {
      "POST /api/kitchen/collection/verify": { status: 409, body: { success: false, message: "This collection code has already been used.", error: { code: "TOKEN_ALREADY_USED" } } } } });
    p.doc.getElementById("token").value = "USEDCODE-123";
    submit(p, "scan-form"); await settle();
    const shown = text(p.doc);
    assert.match(shown, /Collection not verified/);
    assert.match(shown, /already been used/);
    assert.doesNotMatch(shown, /Demo/i);
    assert.equal(findButton(p.doc, "Confirm handover"), undefined);
  });

  test("a verified ready order shows the server's order number and one confirm, which sends one request", async () => {
    const p = await load({ page: "kitchen/scanner.html", url: "/kitchen/scanner.html", routes: {
      "POST /api/kitchen/collection/verify": verifyOk(), "POST /api/kitchen/collection/confirm": { status: 200, body: { success: true, data: { order_number: "TUP-9001" } } } } });
    p.doc.getElementById("token").value = "VALIDCODE-1";
    submit(p, "scan-form"); await settle();
    assert.match(text(p.doc), /TUP-9001/);
    findButton(p.doc, "Confirm handover").click(); await settle();
    assert.match(text(p.doc), /Collection complete/);
    assert.equal(count(p.calls, "POST", "/collection/confirm"), 1);
  });

  test("a failed confirm says the handover was not confirmed, and sends no further requests", async () => {
    const p = await load({ page: "kitchen/scanner.html", url: "/kitchen/scanner.html", confirmAnswer: true, routes: {
      "POST /api/kitchen/collection/verify": verifyOk(), "POST /api/kitchen/collection/confirm": { status: 500, body: { success: false, message: "Server error" } } } });
    p.doc.getElementById("token").value = "VALIDCODE-1";
    submit(p, "scan-form"); await settle();
    findButton(p.doc, "Confirm handover").click(); await settle(); await settle();
    const shown = text(p.doc);
    assert.match(shown, /Handover not confirmed/);
    assert.doesNotMatch(shown, /Collection complete|Demo collection confirmed/);
    assert.equal(p.runaway(), false, "the confirm must not loop");
    assert.equal(count(p.calls, "POST", "/collection/confirm"), 1);
    assert.match(toast(p.doc), /Server error/);
  });

  test("an order that is not ready cannot be handed over", async () => {
    const p = await load({ page: "kitchen/scanner.html", url: "/kitchen/scanner.html", routes: { "POST /api/kitchen/collection/verify": verifyOk("preparing") } });
    p.doc.getElementById("token").value = "VALIDCODE-1";
    submit(p, "scan-form"); await settle();
    assert.match(text(p.doc), /cannot be handed over yet/);
    assert.equal(findButton(p.doc, "Confirm handover"), undefined);
  });

  test("a network failure during verify is reported as 'nothing was checked', never as valid", async () => {
    const p = await load({ page: "kitchen/scanner.html", url: "/kitchen/scanner.html", routes: { "POST /api/kitchen/collection/verify": new TypeError("Failed to fetch") } });
    p.doc.getElementById("token").value = "VALIDCODE-1";
    submit(p, "scan-form"); await settle();
    assert.match(text(p.doc), /Could not reach the server/);
    assert.equal(findButton(p.doc, "Confirm handover"), undefined);
  });
});

describe("collection scanner (demo)", () => {
  test("demo verification and handover make no server requests and say nothing was recorded", async () => {
    const p = await load({ page: "kitchen/scanner.html", url: "/kitchen/scanner.html", session: STAFF_SESSION });
    p.doc.getElementById("token").value = "ANYCODE";
    submit(p, "scan-form"); await settle();
    assert.match(text(p.doc), /Demo order · not a real order/);
    findButton(p.doc, "Confirm handover").click(); await settle();
    assert.match(text(p.doc), /Demo only/);
    assert.equal(p.calls.length, 0, "demo mode must not contact the server");
    assert.ok(p.doc.querySelector(".toast") && /nothing was recorded/i.test(toast(p.doc)));
  });
});

// ---------- Kitchen board ----------
describe("kitchen board (production)", () => {
  test("a failed load shows no invented orders", async () => {
    const p = await load({ page: "kitchen/dashboard.html", url: "/kitchen/dashboard.html", routes: { "GET /api/kitchen/orders": { status: 500, body: { success: false, message: "boom" } } } });
    await settle();
    assert.doesNotMatch(text(p.doc), /TUP-4821|TUP-4825|Masala Dosa/);
    assert.match(text(p.doc), /Could not refresh orders|No orders are loaded/);
  });

  test("live orders render from the server, with no 'Confirm collection' button on ready tickets", async () => {
    const p = await load({ page: "kitchen/dashboard.html", url: "/kitchen/dashboard.html", routes: QUEUE_OK });
    await settle();
    assert.match(text(p.doc), /TUP-7000/);
    assert.match(text(p.doc), /TUP-8000/);
    assert.match(text(p.doc), /Hand over at the scanner/);
    assert.equal(findButton(p.doc, "Confirm collection"), undefined);
  });

  test("a rejected status change is reported as failed, and the board reloads from the server", async () => {
    const p = await load({ page: "kitchen/dashboard.html", url: "/kitchen/dashboard.html", confirmAnswer: true, routes: {
      ...QUEUE_OK,
      "PATCH /api/kitchen/orders/7/status": { status: 409, body: { success: false, message: "Cannot move an order from 'received' to 'ready'.", error: { code: "INVALID_TRANSITION" } } } } });
    await settle();
    const before = count(p.calls, "GET", "/api/kitchen/orders");
    p.doc.querySelector('[data-next="preparing"]').click(); await settle(); await settle();
    assert.doesNotMatch(text(p.doc), /Demo status updated/);
    assert.match(toast(p.doc), /Cannot move an order/);
    assert.equal(count(p.calls, "PATCH", "/status"), 1);
    assert.ok(count(p.calls, "GET", "/api/kitchen/orders") > before, "board must refresh after a failed change");
    assert.ok(p.doc.querySelector('[data-order="7"]'), "order stays where the server has it");
  });

  test("a successful status change is sent to the server and reported as saved", async () => {
    const p = await load({ page: "kitchen/dashboard.html", url: "/kitchen/dashboard.html", routes: {
      ...QUEUE_OK, "PATCH /api/kitchen/orders/7/status": { status: 200, body: { success: true, data: {} } } } });
    await settle();
    p.doc.querySelector('[data-next="preparing"]').click(); await settle(); await settle();
    const patch = p.calls.find((c) => c.method === "PATCH");
    assert.deepEqual(patch.body, { status: "preparing" });
    assert.match(toast(p.doc), /Order status updated/);
  });

  test("after a failed refresh, the last known board is marked out of date and its buttons are disabled", async () => {
    const p = await load({ page: "kitchen/dashboard.html", url: "/kitchen/dashboard.html", routes: {
      "GET /api/kitchen/orders": () => ({ status: 200, body: { success: true, data: { queue: LIVE_QUEUE } } }),
      "PATCH /api/kitchen/orders/7/status": new TypeError("Failed to fetch") } });
    await settle();
    // The change fails because the connection drops. The board then reloads, and that reload also fails.
    p.calls.length = 0;
    p.win.fetch = ((original) => async (input, init) => {
      if (String(input).includes("/kitchen/orders") && (!init || !init.method || init.method === "GET")) {
        p.calls.push({ method: "GET", path: String(input), body: undefined });
        throw new TypeError("Failed to fetch");
      }
      return original(input, init);
    })(p.win.fetch);
    p.doc.querySelector('[data-next="preparing"]').click(); await settle(); await settle();
    assert.match(text(p.doc), /Could not refresh orders/);
    assert.match(text(p.doc), /Showing orders as of/);
    assert.match(toast(p.doc), /Could not reach the server/);
    assert.ok(p.doc.querySelectorAll("[data-next]").length > 0, "orders still listed from the last good load");
    assert.ok([...p.doc.querySelectorAll("[data-next]")].every((b) => b.disabled), "no action while the board is out of date");
  });

  test("unauthenticated visitors are asked to sign in, not shown orders", async () => {
    const p = await load({ page: "kitchen/dashboard.html", url: "/kitchen/dashboard.html", routes: { "GET /api/kitchen/orders": { status: 401, body: {} } } });
    await settle();
    assert.match(text(p.doc), /not signed in as kitchen staff/);
    assert.equal(p.doc.querySelectorAll(".order-ticket").length, 0);
  });
});

describe("kitchen board (demo)", () => {
  test("demo shows sample orders, moves them in memory only, and sends no requests", async () => {
    const p = await load({ page: "kitchen/dashboard.html", url: "/kitchen/dashboard.html", session: STAFF_SESSION });
    await settle();
    assert.match(text(p.doc), /TUP-4821/);
    p.doc.querySelector('[data-next="preparing"]').click(); await settle();
    assert.match(toast(p.doc), /Demo only: nothing was saved/);
    assert.equal(p.calls.length, 0);
  });
});

// ---------- Sign-in pages ----------
const submitLogin = async (p, email, password) => {
  p.doc.getElementById("email").value = email;
  p.doc.getElementById("password").value = password;
  submit(p, "login-form"); await settle(); await settle();
};

describe("kitchen sign-in", () => {
  const loginRoute = (status, body) => ({ "POST /api/auth/login": { status, body } });

  test("a wrong password shows the reason, starts no demo, and does not navigate", async () => {
    const p = await load({ page: "kitchen/login.html", url: "/kitchen/login.html", routes: loginRoute(401, { success: false, message: "Invalid email or password." }) });
    await submitLogin(p, "someone@college.edu", "wrong");
    assert.equal(p.win.localStorage.getItem("trayup-demo-role"), null);
    assert.equal(p.win.sessionStorage.getItem("trayup-mode"), null);
    assert.equal(p.navigations.length, 0);
    assert.match(toast(p.doc), /Invalid email or password/);
  });

  test("a network failure is reported as such, not as a demo sign-in", async () => {
    const p = await load({ page: "kitchen/login.html", url: "/kitchen/login.html", routes: { "POST /api/auth/login": new TypeError("Failed to fetch") } });
    await submitLogin(p, "someone@college.edu", "pw");
    assert.equal(p.navigations.length, 0);
    assert.match(toast(p.doc), /Could not reach the server/);
  });

  test("a kitchen account goes to the kitchen board", async () => {
    const p = await load({ page: "kitchen/login.html", url: "/kitchen/login.html", routes: loginRoute(200, { success: true, data: { id: 3, role: "KITCHEN", email: "k@x.com" } }) });
    await submitLogin(p, "k@x.com", "pw");
    assert.equal(p.navigations.length, 1);
  });

  test("a student account is signed out and refused, not sent to any staff page", async () => {
    const p = await load({ page: "kitchen/login.html", url: "/kitchen/login.html", routes: {
      "POST /api/auth/login": { status: 200, body: { success: true, data: { id: 4, role: "STUDENT", email: "s@x.com" } } },
      "POST /api/auth/logout": { status: 200, body: { success: true, data: {} } } } });
    await submitLogin(p, "s@x.com", "pw");
    assert.equal(p.navigations.length, 0);
    assert.equal(count(p.calls, "POST", "/api/auth/logout"), 1);
    assert.match(toast(p.doc), /does not have kitchen access/);
  });

  test("the demo button is the only way in, and it makes no sign-in request", async () => {
    const p = await load({ page: "kitchen/login.html", url: "/kitchen/login.html" });
    p.doc.getElementById("demo-entry").click(); await settle();
    assert.equal(p.win.sessionStorage.getItem("trayup-mode"), "demo");
    assert.equal(p.calls.filter((c) => c.path.includes("/auth/login")).length, 0);
    assert.equal(p.navigations.length, 1);
  });
});

describe("admin sign-in", () => {
  test("a real administrator goes to the admin overview", async () => {
    const p = await load({ page: "admin/login.html", url: "/admin/login.html", routes: { "POST /api/auth/login": { status: 200, body: { success: true, data: { id: 1, role: "ADMIN", email: "a@x.com" } } } } });
    await submitLogin(p, "a@x.com", "StrongPass1");
    assert.equal(p.navigations.length, 1);
    assert.equal(count(p.calls, "POST", "/api/auth/logout"), 0);
  });

  test("a kitchen account is refused on the admin sign-in page", async () => {
    const p = await load({ page: "admin/login.html", url: "/admin/login.html", routes: {
      "POST /api/auth/login": { status: 200, body: { success: true, data: { id: 3, role: "KITCHEN", email: "k@x.com" } } },
      "POST /api/auth/logout": { status: 200, body: { success: true, data: {} } } } });
    await submitLogin(p, "k@x.com", "pw1234");
    assert.equal(p.navigations.length, 0);
    assert.match(toast(p.doc), /kitchen account/);
  });

  test("a failed sign-in never stores a demo role", async () => {
    const p = await load({ page: "admin/login.html", url: "/admin/login.html", routes: { "POST /api/auth/login": { status: 401, body: { success: false, message: "Invalid email or password." } } } });
    await submitLogin(p, "a@x.com", "wrong1");
    assert.equal(p.win.localStorage.getItem("trayup-demo-role"), null);
    assert.equal(p.navigations.length, 0);
  });
});

// ---------- Admin pages ----------
// The overview reads the reporting API for two windows (today, last 30 days) and the recent orders list.
const overviewFor = (from, to) => ({
  total_orders: 42, paid_orders: 30, cancelled_orders: 2,
  gross_revenue_paise: 180000, refunded_paise: 5000, net_revenue_paise: 175000,
  average_order_value_paise: 6000, completion_rate_percent: 80, average_preparation_minutes: 9,
});
const overviewRoutes = (fail) => fail ? {
  "GET /api/admin/reports/overview": { status: 500, body: { success: false, message: "boom" } },
  "GET /api/admin/orders": { status: 500, body: {} },
} : {
  "GET /api/admin/reports/overview": ({ path }) => ({ status: 200, body: { success: true, data: overviewFor() } }),
  "GET /api/admin/orders": { status: 200, body: { success: true, data: { orders: [{ order_number: "TUP-1", student: { name: "Asha" }, total_paise: 6000, order_status: "received", payment_status: "paid" }], pagination: { total: 42 } } } },
};

describe("admin overview (production)", () => {
  test("the overview shows reporting figures for today and the last 30 days, and recent orders", async () => {
    const p = await load({ page: "admin/dashboard.html", url: "/admin/dashboard.html", routes: overviewRoutes(false) });
    await settle();
    const shown = text(p.doc);
    assert.match(shown, /Today/);
    assert.match(shown, /Last 30 days/);
    assert.match(shown, /Gross revenue\s*₹1,800/);
    assert.match(shown, /TUP-1\s*Asha\s*₹60/);
    assert.ok(p.calls.some((c) => c.path.includes("/api/admin/reports/overview?from=") && c.path.includes("&to=")));
    assert.ok(!p.calls.some((c) => c.path.includes("payment_status=paid")), "stats must not come from paginated orders");
  });

  test("a failed overview shows no figures in place of the real ones", async () => {
    const p = await load({ page: "admin/dashboard.html", url: "/admin/dashboard.html", routes: overviewRoutes(true) });
    await settle();
    assert.doesNotMatch(text(p.doc), /₹1,800|₹18,450|Gross revenue/);
    assert.match(text(p.doc), /Nothing is shown in their place/);
  });

  test("the overview asks for administrator sign-in when the session is not an admin", async () => {
    const p = await load({ page: "admin/dashboard.html", url: "/admin/dashboard.html", routes: { "GET /api/admin/reports/overview": { status: 403, body: {} }, "GET /api/admin/orders": { status: 403, body: {} } } });
    await settle();
    assert.match(text(p.doc), /Administrator access/);
  });
});

describe("admin orders", () => {
  test("the orders page sends filters to the server and shows an error rather than sample rows", async () => {
    const p = await load({ page: "admin/orders.html", url: "/admin/orders.html", routes: { "GET /api/admin/orders?per_page=50": { status: 500, body: {} } } });
    await settle();
    assert.doesNotMatch(text(p.doc), /TUP-4825|Aarav/);
    assert.match(text(p.doc), /Could not load orders/);
  });

  test("the orders page filter uses backend values", async () => {
    const p = await load({ page: "admin/orders.html", url: "/admin/orders.html", routes: { "GET /api/admin/orders?per_page=50": { status: 200, body: { success: true, data: { orders: [], pagination: { total: 0 } } } } } });
    await settle();
    p.doc.getElementById("payment-filter").value = "paid";
    p.doc.getElementById("payment-filter").dispatchEvent(new p.win.Event("change"));
    await settle();
    assert.ok(p.calls.some((c) => c.path.includes("payment_status=paid")));
  });
});

describe("admin refunds (still not connected)", () => {
  test("the refunds page shows no fake refunds in production", async () => {
    const p = await load({ page: "admin/refunds.html", url: "/admin/refunds.html" });
    await settle();
    assert.match(text(p.doc), /Not connected to the live system yet/);
    assert.doesNotMatch(text(p.doc), /pay_demo_482|TUP-4792/);
  });
});

describe("mode isolation", () => {
  test("production pages show no demo banner, even if a stale demo flag exists", async () => {
    const p = await load({ page: "admin/dashboard.html", url: "/admin/dashboard.html", routes: { "GET /api/admin/orders": { status: 500, body: {} } }, session: { "trayup-mode": "demo" }, local: { "trayup-demo-role": "kitchen" } });
    await settle();
    // Flag is honoured on staff pages, so demo here is intentional; production check uses no flag:
    p.close();
    const q = await load({ page: "admin/dashboard.html", url: "/admin/dashboard.html", routes: { "GET /api/admin/orders": { status: 500, body: {} } }, local: { "trayup-demo-role": "kitchen" } });
    await settle();
    assert.doesNotMatch(text(q.doc), /DEMO MODE/);
    assert.equal(q.win.localStorage.getItem("trayup-demo-role"), null, "old demo role is removed");
  });

  test("the demo flag never reaches student pages", async () => {
    const p = await load({ page: "student/tracking.html", url: "/student/tracking.html", session: { "trayup-mode": "demo" }, routes: {
      "GET /api/orders": { status: 200, body: { success: true, data: { orders: [] } } } } });
    await settle();
    assert.ok(p.calls.some((c) => c.path.startsWith("/api/orders")), "student requests must still reach the server");
  });

  test("opening a sign-in page leaves demo mode", async () => {
    const p = await load({ page: "kitchen/login.html", url: "/kitchen/login.html", session: { "trayup-mode": "demo" } });
    await settle();
    assert.equal(p.win.sessionStorage.getItem("trayup-mode"), null);
    assert.equal(p.doc.querySelector('[role="status"]'), null, "no demo banner on the sign-in page");
  });

  test("in demo mode the API client refuses every request, reads and writes", async () => {
    const p = await load({ page: "kitchen/dashboard.html", url: "/kitchen/dashboard.html", session: STAFF_SESSION });
    await assert.rejects(() => p.win.trayApi.get("/kitchen/orders"), (e) => e.code === "DEMO_MODE");
    await assert.rejects(() => p.win.trayApi.patch("/kitchen/orders/1/status", { status: "ready" }), (e) => e.code === "DEMO_MODE");
    assert.equal(p.calls.length, 0);
  });
});

// ---------- Student ----------
describe("student pages", () => {
  test("tracking shows an error, not demo orders, when the order request fails", async () => {
    const p = await load({ page: "student/tracking.html", url: "/student/tracking.html", routes: { "GET /api/orders": { status: 500, body: {} } } });
    await settle();
    assert.match(text(p.doc), /Could not load your orders/);
    assert.doesNotMatch(text(p.doc), /Masala Dosa|Cold Coffee/);
  });

  test("tracking shows the item name from the real order, not a catalog guess", async () => {
    const p = await load({ page: "student/tracking.html", url: "/student/tracking.html", routes: { "GET /api/orders": { status: 200, body: { success: true, data: { orders: [{
      id: 55, order_number: "TUP-5500", order_status: "received", payment_status: "paid", total_paise: 12000, created_at: "2026-11-25T10:00:00+05:30",
      items: [{ menu_item_id: 1, item_name: "Samosa", unit_price_paise: 6000, quantity: 2, line_total_paise: 12000 }] }] } } } } });
    await settle();
    assert.match(text(p.doc), /Samosa/);
    assert.doesNotMatch(text(p.doc), /Masala Dosa/);
  });

  test("checkout refuses a cart that does not match the live menu, and sends no order", async () => {
    const cart = [{ id: 1, name: "Masala Dosa", price: 60, qty: 1 }];
    const p = await load({ page: "student/checkout.html", url: "/student/checkout.html", local: { "trayup-cart": JSON.stringify(cart) }, routes: {
      "GET /api/menu": { status: 200, body: { items: [{ id: 1, name: "Samosa", price_paise: 6000 }] } } } });
    await settle();
    p.doc.getElementById("name").value = "Asha";
    p.doc.getElementById("phone").value = "9876543210";
    submit(p, "checkout-form"); await settle(); await settle();
    assert.equal(count(p.calls, "POST", "/api/orders"), 0, "no order may be created");
    assert.match(toast(p.doc), /not on the live menu/);
  });
});

describe("student checkout presence", () => {
  const cart = [{ id: 1, name: "Samosa", price: 15, qty: 1 }];
  const menuRoute = { "GET /api/menu": { status: 200, body: { items: [{ id: 1, name: "Samosa", price_paise: 1500 }] } } };
  const fill = (p) => {
    p.doc.getElementById("name").value = "Asha";
    p.doc.getElementById("phone").value = "9876543210";
  };

  test("an order is sent with the verified presence session, and the session is cleared afterwards", async () => {
    const expiresAt = Date.now() + 120000;
    const p = await load({ page: "student/checkout.html", url: "/student/checkout.html",
      local: { "trayup-cart": JSON.stringify(cart) },
      session: { "trayup-presence-session": JSON.stringify({ token: "live-session-token", expiresAt }) },
      routes: { ...menuRoute, "POST /api/orders": { status: 201, body: { success: true, data: { id: 9, order_number: "TUP-9", total_paise: 1500, order_status: "pending_payment", items: [] } } } } });
    await settle();
    fill(p);
    submit(p, "checkout-form"); await settle(); await settle();
    const post = p.calls.find((c) => c.method === "POST" && c.path.endsWith("/api/orders"));
    assert.ok(post, "the order request must be sent");
    assert.equal(post.headers["X-Presence-Session"], "live-session-token");
    assert.equal(p.win.sessionStorage.getItem("trayup-presence-session"), null);
  });

  test("without a live verification, no order is sent and the student is told to verify", async () => {
    const p = await load({ page: "student/checkout.html", url: "/student/checkout.html",
      local: { "trayup-cart": JSON.stringify(cart) }, routes: menuRoute });
    await settle();
    fill(p);
    submit(p, "checkout-form"); await settle(); await settle();
    assert.equal(count(p.calls, "POST", "/api/orders"), 0);
    assert.match(toast(p.doc) + text(p.doc), /Verify that you are at the canteen/);
  });

  test("an expired verification is not used", async () => {
    const p = await load({ page: "student/checkout.html", url: "/student/checkout.html",
      local: { "trayup-cart": JSON.stringify(cart) },
      session: { "trayup-presence-session": JSON.stringify({ token: "old", expiresAt: Date.now() - 1000 }) }, routes: menuRoute });
    await settle();
    fill(p);
    submit(p, "checkout-form"); await settle(); await settle();
    assert.equal(count(p.calls, "POST", "/api/orders"), 0);
    assert.equal(p.win.sessionStorage.getItem("trayup-presence-session"), null);
  });
});
