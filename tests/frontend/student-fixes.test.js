// Student pages: paged order tracking, and a checkout key that survives a refresh.
const { test, describe, afterEach } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const { loadPage, settle, text } = require("./harness");

const ROOT = process.env.FRONTEND_ROOT || path.resolve(__dirname, "../../frontend");
const open = [];
afterEach(() => { while (open.length) { try { open.pop().close(); } catch (_) {} } });
const load = async (opts) => { const p = await loadPage({ root: ROOT, ...opts }); open.push(p); return p; };
const button = (p, selector) => p.doc.querySelector(selector);

const order = (n) => ({
  id: n, order_number: `TUP-${1000 + n}`, order_status: "received", payment_status: "paid",
  subtotal_paise: 1000, discount_paise: 0, tax_paise: 0, total_paise: 1000, items: [],
  created_at: "2026-02-10T04:30:00+00:00", updated_at: "2026-02-10T04:30:00+00:00",
});
const page = (from, to, total, hasNext) => ({
  success: true, message: "", data: {
    orders: Array.from({ length: to - from + 1 }, (_, i) => order(from + i)),
    pagination: { page: Math.ceil(from / 10), per_page: 10, total, pages: Math.ceil(total / 10), has_next: hasNext, has_prev: false },
  },
});

describe("order tracking pages through every order", () => {
  test("the first request asks for one page of ten", async () => {
    const p = await load({ page: "student/tracking.html", url: "/student/tracking.html", routes: {
      "GET /api/orders": { status: 200, body: page(1, 10, 25, true) },
    } });
    await settle(); await settle();
    const requested = p.calls.find((c) => c.path.includes("/api/orders"));
    assert.match(requested.path, /page=1&per_page=10/);
  });

  test("a Load more button appears while more orders exist, and appends the next page", async () => {
    const p = await load({ page: "student/tracking.html", url: "/student/tracking.html", routes: {
      "GET /api/orders": (req) => req.path.includes("page=2") ? { status: 200, body: page(11, 20, 25, true) } : { status: 200, body: page(1, 10, 25, true) },
    } });
    await settle(); await settle();
    assert.match(text(p.doc), /TUP-1001/);
    assert.doesNotMatch(text(p.doc), /TUP-1011/);
    button(p, "[data-load-more]").click();
    await settle(); await settle();
    assert.match(text(p.doc), /TUP-1011/);
    assert.match(text(p.doc), /TUP-1001/, "earlier orders stay on the page");
  });

  test("the button disappears when there are no more orders", async () => {
    const p = await load({ page: "student/tracking.html", url: "/student/tracking.html", routes: {
      "GET /api/orders": { status: 200, body: page(1, 5, 5, false) },
    } });
    await settle(); await settle();
    assert.equal(button(p, "[data-load-more]"), null);
  });

  test("a failed Load more keeps the orders already shown and says so", async () => {
    const p = await load({ page: "student/tracking.html", url: "/student/tracking.html", routes: {
      "GET /api/orders": (req) => req.path.includes("page=2") ? new TypeError("Failed to fetch") : { status: 200, body: page(1, 10, 25, true) },
    } });
    await settle(); await settle();
    button(p, "[data-load-more]").click();
    await settle(); await settle();
    assert.match(text(p.doc), /TUP-1001/);
    assert.match(text(p.doc), /We couldn’t load more orders/);
    assert.ok(button(p, "[data-load-more]"), "the button stays so the student can try again");
  });
});

describe("checkout keeps its idempotency key across a refresh", () => {
  const CART = JSON.stringify([{ id: 1, name: "Samosa", price: 15, qty: 2 }]);
  const fill = (p) => {
    p.doc.getElementById("name").value = "Asha";
    p.doc.getElementById("phone").value = "9876543210";
  };
  const submit = (p) => p.doc.getElementById("checkout-form").dispatchEvent(new p.win.Event("submit", { cancelable: true, bubbles: true }));
  const orderPosts = (p) => p.calls.filter((c) => c.method === "POST" && c.path.endsWith("/api/orders"));

  test("a dropped order request is retried after a refresh with the same key, and the key is cleared on success", async () => {
    let attempt = 0;
    const routes = {
      "POST /api/orders": () => {
        attempt += 1;
        if (attempt === 1) return new TypeError("Failed to fetch");
        return { status: 201, body: { success: true, message: "", data: { id: 9, order_number: "TUP-1009", total_paise: 3000, order_status: "pending_payment", payment_status: "pending", items: [] } } };
      },
    };
    const first = await load({ page: "student/checkout.html", url: "/student/checkout.html", local: { "trayup-cart": CART }, routes });
    await settle();
    fill(first);
    submit(first);
    await settle(); await settle();
    const firstKey = orderPosts(first)[0].headers["Idempotency-Key"];
    assert.ok(firstKey, "the first attempt sends a key");
    const saved = first.win.sessionStorage.getItem("trayup-checkout-key");
    assert.ok(saved, "the key is kept after a failed attempt");

    // A refresh is a new page load with the same tab storage.
    const second = await load({ page: "student/checkout.html", url: "/student/checkout.html",
      local: { "trayup-cart": CART }, session: { "trayup-checkout-key": saved }, routes });
    await settle();
    fill(second);
    submit(second);
    await settle(); await settle();
    assert.equal(orderPosts(second)[0].headers["Idempotency-Key"], firstKey, "the retry reuses the key");
    assert.equal(second.win.sessionStorage.getItem("trayup-checkout-key"), null, "the key is cleared once the order exists");
  });

  test("changing the cart gives the next order a new key", async () => {
    const p = await load({ page: "student/checkout.html", url: "/student/checkout.html", local: { "trayup-cart": CART },
      session: { "trayup-checkout-key": JSON.stringify({ key: "old-key", fingerprint: JSON.stringify([[9, 9]]) }) },
      routes: { "POST /api/orders": new TypeError("Failed to fetch") } });
    await settle();
    fill(p);
    submit(p);
    await settle(); await settle();
    assert.notEqual(orderPosts(p)[0].headers["Idempotency-Key"], "old-key");
  });
});
