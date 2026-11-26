// Student order pages: checkout sends the typed details, the confirmation page shows the order the
// server saved, and the buttons on the animated page lead somewhere.
const { test, describe, afterEach } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const { loadPage, settle, text, wait } = require("./harness");

const ROOT = process.env.FRONTEND_ROOT || path.resolve(__dirname, "../../frontend");
const open = [];
afterEach(() => { while (open.length) { try { open.pop().close(); } catch (_) {} } });
const load = async (opts) => { const p = await loadPage({ root: ROOT, ...opts }); open.push(p); return p; };

const SERVER_ORDER = {
  id: 7, order_number: "TU2611270001", order_status: "pending_payment", payment_status: "pending",
  subtotal_paise: 1000, discount_paise: 0, tax_paise: 0, total_paise: 1000,
  customer_name: "Asha Rao", customer_phone: "+919876543210", instructions: "Less sugar",
  items: [{ menu_item_id: 1, item_name: "Samosa", unit_price_paise: 1000, quantity: 2, line_total_paise: 2000 }],
  created_at: "2026-11-27T04:30:00+00:00", updated_at: "2026-11-27T04:30:00+00:00",
};
const orderResponse = (order) => ({ status: 200, body: { success: true, message: "", data: order } });

describe("confirmation shows the order the server saved", () => {
  test("it loads the order by id and ignores anything stored in the browser", async () => {
    const p = await load({
      page: "student/confirmation.html", url: "/student/confirmation.html?order_id=7",
      local: { "trayup-last-order": JSON.stringify({ success: true, data: { order_number: "FAKE", student_name: "Someone Else", payment_status: "paid" } }) },
      routes: { "GET /api/orders/7": orderResponse(SERVER_ORDER) },
    });
    await settle(); await settle();

    assert.ok(p.calls.some((c) => c.method === "GET" && c.path === "/api/orders/7"), "the order is fetched from the server");
    const body = text(p.doc);
    assert.match(body, /TU2611270001/);
    assert.match(body, /Asha Rao/);
    assert.match(body, /\+919876543210/);
    assert.match(body, /Less sugar/);
    assert.doesNotMatch(body, /FAKE|Someone Else/, "the stored copy is not shown");
    assert.equal(p.navigations.length, 0, "an unpaid order stays on this page");
  });

  test("without an order id it says the order was not found and makes no order request", async () => {
    const p = await load({ page: "student/confirmation.html", url: "/student/confirmation.html", routes: {} });
    await settle(); await settle();

    assert.match(text(p.doc), /couldn’t find this order/);
    assert.equal(p.calls.filter((c) => c.path.startsWith("/api/orders/")).length, 0);
  });

  test("an order that is not the student's shows not found, not the details", async () => {
    const p = await load({
      page: "student/confirmation.html", url: "/student/confirmation.html?order_id=99",
      routes: { "GET /api/orders/99": { status: 404, body: { success: false, message: "Order not found.", error: { code: "ORDER_NOT_FOUND" } } } },
    });
    await settle(); await settle();

    assert.match(text(p.doc), /couldn’t find this order/);
    assert.doesNotMatch(text(p.doc), /Asha/);
  });

  test("a signed-out visitor is sent to log in", async () => {
    const p = await load({
      page: "student/confirmation.html", url: "/student/confirmation.html?order_id=7",
      routes: { "GET /api/orders/7": { status: 401, body: { success: false, message: "Please log in first.", error: { code: "AUTH_REQUIRED" } } } },
    });
    await settle(); await settle();

    assert.ok(p.navigations.length > 0, "the page tries to leave for the login page");
  });

  test("the track link carries the order id", async () => {
    const p = await load({
      page: "student/confirmation.html", url: "/student/confirmation.html?order_id=7",
      routes: { "GET /api/orders/7": orderResponse(SERVER_ORDER) },
    });
    await settle(); await settle();

    const trackYourOrder = [...p.doc.querySelectorAll("a")].find((a) => a.textContent.trim() === "Track your order");
    assert.ok(trackYourOrder, "the Track your order link is on the page");
    assert.match(trackYourOrder.getAttribute("href"), /tracking\.html\?order_id=7$/);
  });
});

describe("the animated confirmation buttons do what they say", () => {
  const animated = (query) => load({
    page: "student/order-placed-animation.html",
    url: `/student/order-placed-animation.html?receipt=TU2611270001${query || ""}`,
    routes: {},
  });

  test("Track My Order shows a message and then leaves for the order's tracking page", async () => {
    const p = await animated("&order_id=7");
    p.doc.getElementById("trackBtn").click();
    await wait(600);

    assert.match(text(p.doc), /Opening your orders/);
    assert.ok(p.navigations.length > 0, "the page navigates away");
  });

  test("Continue Shopping leaves for the menu", async () => {
    const p = await animated("&order_id=7");
    p.doc.getElementById("contBtn").click();
    await wait(600);

    assert.match(text(p.doc), /Taking you back to the menu/);
    assert.ok(p.navigations.length > 0, "the page navigates away");
  });

  test("the receipt number on the page is the one from the link", async () => {
    const p = await animated("&order_id=7");
    assert.equal(p.doc.getElementById("copy").textContent, "TU2611270001");
  });
});

describe("tracking opens the order it was linked to", () => {
  test("an order id in the link is accepted and the orders still render", async () => {
    const p = await load({
      page: "student/tracking.html", url: "/student/tracking.html?order_id=7",
      routes: { "GET /api/orders": { status: 200, body: { success: true, message: "", data: { orders: [SERVER_ORDER], pagination: { page: 1, per_page: 10, total: 1, pages: 1, has_next: false, has_prev: false } } } } },
    });
    await settle(); await settle();

    assert.match(text(p.doc), /TU2611270001/);
    assert.ok(p.doc.querySelector('[data-order="7"]'), "the matching order card is on the page");
  });
});

describe("checkout sends the typed details to the server", () => {
  const CART = JSON.stringify([{ id: 1, name: "Samosa", price: 10, qty: 2 }]);
  const fill = (p, name = "Asha", instructions = "Less sugar") => {
    p.doc.getElementById("name").value = name;
    p.doc.getElementById("phone").value = "9876543210";
    p.doc.getElementById("instructions").value = instructions;
  };
  const submit = (p) => p.doc.getElementById("checkout-form").dispatchEvent(new p.win.Event("submit", { cancelable: true, bubbles: true }));
  const orderPosts = (p) => p.calls.filter((c) => c.method === "POST" && c.path.endsWith("/api/orders"));
  const created = { status: 201, body: { success: true, message: "", data: { id: 7, order_number: "TU2611270001", total_paise: 2000, order_status: "pending_payment", payment_status: "pending", items: [] } } };

  test("the order request carries the name, phone and instructions", async () => {
    const p = await load({ page: "student/checkout.html", url: "/student/checkout.html", local: { "trayup-cart": CART }, routes: { "POST /api/orders": created } });
    await settle();
    fill(p);
    p.doc.querySelector('input[name="payment_method"][value="cash"]').checked = true;
    submit(p);
    await settle(); await settle();

    const body = orderPosts(p)[0].body;
    assert.equal(body.customer_name, "Asha");
    assert.equal(body.customer_phone, "9876543210");
    assert.equal(body.instructions, "Less sugar");
    assert.deepEqual(body.items, [{ menu_item_id: 1, quantity: 2 }]);
  });

  test("a cash order goes to its confirmation page by id, and nothing is saved in browser storage", async () => {
    const p = await load({ page: "student/checkout.html", url: "/student/checkout.html", local: { "trayup-cart": CART }, routes: { "POST /api/orders": created } });
    await settle();
    fill(p);
    p.doc.querySelector('input[name="payment_method"][value="cash"]').checked = true;
    submit(p);
    await settle(); await settle();

    assert.ok(p.navigations.length > 0, "the page moves on to the confirmation");
    assert.equal(p.win.localStorage.getItem("trayup-last-order"), null, "no copy of the order is stored in the browser");
    assert.equal(p.win.localStorage.getItem("trayup-cart"), null, "the cart is cleared");
  });

  test("changing the typed name gives the next attempt a new idempotency key", async () => {
    let attempt = 0;
    const routes = {
      "POST /api/orders": () => {
        attempt += 1;
        return attempt === 1 ? new TypeError("Failed to fetch") : created;
      },
    };
    const first = await load({ page: "student/checkout.html", url: "/student/checkout.html", local: { "trayup-cart": CART }, routes });
    await settle();
    fill(first, "Asha");
    submit(first);
    await settle(); await settle();
    const firstKey = orderPosts(first)[0].headers["Idempotency-Key"];

    const second = await load({ page: "student/checkout.html", url: "/student/checkout.html", local: { "trayup-cart": CART },
      session: { "trayup-checkout-key": first.win.sessionStorage.getItem("trayup-checkout-key") }, routes });
    await settle();
    fill(second, "Ravi");
    submit(second);
    await settle(); await settle();

    assert.notEqual(orderPosts(second)[0].headers["Idempotency-Key"], firstKey, "different details are a different request");
  });
});

describe("a paid-out or expired order is not reused under its key", () => {
  const CART = JSON.stringify([{ id: 1, name: "Samosa", price: 10, qty: 2 }]);
  const fill = (p) => {
    p.doc.getElementById("name").value = "Asha";
    p.doc.getElementById("phone").value = "9876543210";
  };
  const submit = (p) => p.doc.getElementById("checkout-form").dispatchEvent(new p.win.Event("submit", { cancelable: true, bubbles: true }));
  const orderPosts = (p) => p.calls.filter((c) => c.method === "POST" && c.path.endsWith("/api/orders"));

  test("after ORDER_CANCELLED the next submit sends a new key and creates a new order", async () => {
    let attempt = 0;
    const routes = {
      "POST /api/orders": () => {
        attempt += 1;
        if (attempt === 1) {
          return { status: 409, body: { success: false, message: "This order was cancelled. Place a new order.", error: { code: "ORDER_CANCELLED" } } };
        }
        return { status: 201, body: { success: true, message: "", data: { id: 8, order_number: "TU2611270002", total_paise: 2000, order_status: "pending_payment", payment_status: "pending", items: [] } } };
      },
    };
    const p = await load({ page: "student/checkout.html", url: "/student/checkout.html", local: { "trayup-cart": CART }, routes });
    await settle();
    fill(p);
    p.doc.querySelector('input[name="payment_method"][value="cash"]').checked = true;
    submit(p);
    await settle(); await settle();
    const firstKey = orderPosts(p)[0].headers["Idempotency-Key"];
    assert.match(text(p.doc), /This order was cancelled/);

    submit(p);
    await settle(); await settle();
    const secondKey = orderPosts(p)[1].headers["Idempotency-Key"];
    assert.notEqual(secondKey, firstKey, "the cancelled order's key is not sent again");
    assert.ok(p.navigations.length > 0, "the new order is created and the page moves on");
  });
});
