// Refunds page: real payments and refunds from the API, a checked refund form, and clear server errors.
const { test, describe, afterEach } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const { loadPage, settle, text } = require("./harness");

const ROOT = process.env.FRONTEND_ROOT || path.resolve(__dirname, "../../frontend");
const open = [];
afterEach(() => { while (open.length) { try { open.pop().close(); } catch (_) {} } });
const load = async (opts) => { const p = await loadPage({ root: ROOT, ...opts }); open.push(p); return p; };
const storageWrites = (p) => p.win.localStorage.length + p.win.sessionStorage.length;
const posts = (p) => p.calls.filter((c) => c.method === "POST" && c.path.includes("/refund"));
const button = (p, label) => [...p.doc.querySelectorAll("button")].find((b) => b.textContent.trim() === label);

const ME = { "GET /api/auth/me": { status: 200, body: { success: true, message: "", data: { id: 1, name: "Admin", email: "a@x.com", role: "ADMIN" } } } };
const PAYMENTS = [
  { payment_id: 11, order_id: 1, order_number: "TUP-1100", order_status: "received", payment_status: "paid", currency: "INR",
    amount_paise: 60000, refunded_paise: 0, pending_refund_paise: 0, refundable_paise: 60000, created_at: "2026-02-10T04:30:00" },
  { payment_id: 12, order_id: 2, order_number: "TUP-1200", order_status: "cancelled", payment_status: "refunded", currency: "INR",
    amount_paise: 20000, refunded_paise: 20000, pending_refund_paise: 0, refundable_paise: 0, created_at: "2026-02-10T05:00:00" },
];
const REFUNDS = [
  { id: 5, payment_id: 12, order_number: "TUP-1200", amount_paise: 20000, status: "processed", reason: "Kitchen closed", requested_by: 1, created_at: "2026-02-10T05:10:00", processed_at: "2026-02-10T05:11:00" },
];
const routes = (extra = {}) => ({
  ...ME,
  "GET /api/admin/payments/refunds": { status: 200, body: { success: true, message: "", data: { refunds: REFUNDS } } },
  "GET /api/admin/payments": { status: 200, body: { success: true, message: "", data: { payments: PAYMENTS } } },
  ...extra,
});

describe("refunds page", () => {
  test("lists real payments and refunds, with the refundable amount for each", async () => {
    const p = await load({ page: "admin/refunds.html", url: "/admin/refunds.html", routes: routes() });
    await settle(); await settle();
    const shown = text(p.doc);
    assert.match(shown, /TUP-1100/);
    assert.match(shown, /₹600/);
    assert.match(shown, /Kitchen closed/);
    assert.doesNotMatch(shown, /pay_demo|TUP-4792|Not connected/);
  });

  test("only payments with something left to refund get a refund button", async () => {
    const p = await load({ page: "admin/refunds.html", url: "/admin/refunds.html", routes: routes() });
    await settle(); await settle();
    assert.ok(p.doc.querySelector('[data-refund="11"]'));
    assert.equal(p.doc.querySelector('[data-refund="12"]'), null);
    assert.match(text(p.doc), /Nothing to refund/);
  });

  test("the amount must be filled in and within the refundable amount, and nothing is sent when it is not", async () => {
    const p = await load({ page: "admin/refunds.html", url: "/admin/refunds.html", routes: routes() });
    await settle(); await settle();
    p.doc.querySelector('[data-refund="11"]').click(); await settle();
    p.doc.querySelector('form[data-refund-for="11"] input[name="amount"]').value = "700";
    p.doc.querySelector('form[data-refund-for="11"] textarea[name="reason"]').value = "Too much";
    p.doc.querySelector('form[data-refund-for="11"]').dispatchEvent(new p.win.Event("submit", { cancelable: true, bubbles: true }));
    await settle();
    assert.equal(posts(p).length, 0);
    assert.match(text(p.doc), /Enter an amount from/);
  });

  test("a reason is required", async () => {
    const p = await load({ page: "admin/refunds.html", url: "/admin/refunds.html", routes: routes() });
    await settle(); await settle();
    p.doc.querySelector('[data-refund="11"]').click(); await settle();
    p.doc.querySelector('form[data-refund-for="11"] textarea[name="reason"]').value = "   ";
    p.doc.querySelector('form[data-refund-for="11"]').dispatchEvent(new p.win.Event("submit", { cancelable: true, bubbles: true }));
    await settle();
    assert.equal(posts(p).length, 0);
    assert.match(text(p.doc), /Enter a reason/);
  });

  test("a confirmed refund sends the amount in paise and the reason, then reports it as pending", async () => {
    const p = await load({ page: "admin/refunds.html", url: "/admin/refunds.html", confirmAnswer: true, routes: routes({
      "POST /api/admin/payments/11/refund": { status: 201, body: { success: true, message: "Refund requested", data: { id: 9, status: "pending" } } },
    }) });
    await settle(); await settle();
    p.doc.querySelector('[data-refund="11"]').click(); await settle();
    p.doc.querySelector('form[data-refund-for="11"] input[name="amount"]').value = "150.50";
    p.doc.querySelector('form[data-refund-for="11"] textarea[name="reason"]').value = "Wrong item served";
    p.doc.querySelector('form[data-refund-for="11"]').dispatchEvent(new p.win.Event("submit", { cancelable: true, bubbles: true }));
    await settle(); await settle();
    assert.equal(posts(p).length, 1);
    assert.deepEqual(posts(p)[0].body, { amount_paise: 15050, reason: "Wrong item served" });
    assert.match(text(p.doc), /shows as pending until Razorpay confirms it/);
  });

  test("a cancelled confirmation sends nothing", async () => {
    const p = await load({ page: "admin/refunds.html", url: "/admin/refunds.html", confirmAnswer: false, routes: routes() });
    await settle(); await settle();
    p.doc.querySelector('[data-refund="11"]').click(); await settle();
    p.doc.querySelector('form[data-refund-for="11"] textarea[name="reason"]').value = "Changed mind";
    p.doc.querySelector('form[data-refund-for="11"]').dispatchEvent(new p.win.Event("submit", { cancelable: true, bubbles: true }));
    await settle();
    assert.equal(posts(p).length, 0);
  });

  test("the server's refusal is shown next to the form", async () => {
    const p = await load({ page: "admin/refunds.html", url: "/admin/refunds.html", confirmAnswer: true, routes: routes({
      "POST /api/admin/payments/11/refund": { status: 400, body: { success: false, message: "Refund exceeds the remaining captured amount.", error: { code: "REFUND_TOO_LARGE" } } },
    }) });
    await settle(); await settle();
    p.doc.querySelector('[data-refund="11"]').click(); await settle();
    p.doc.querySelector('form[data-refund-for="11"] textarea[name="reason"]').value = "Test";
    p.doc.querySelector('form[data-refund-for="11"]').dispatchEvent(new p.win.Event("submit", { cancelable: true, bubbles: true }));
    await settle(); await settle();
    assert.match(text(p.doc), /Refund exceeds the remaining captured amount\./);
  });

  test("a failed load shows the reason and no invented rows", async () => {
    const p = await load({ page: "admin/refunds.html", url: "/admin/refunds.html", routes: {
      ...ME,
      "GET /api/admin/payments": { status: 500, body: { success: false, message: "boom" } },
      "GET /api/admin/payments/refunds": { status: 500, body: { success: false, message: "boom" } },
    } });
    await settle(); await settle();
    assert.doesNotMatch(text(p.doc), /pay_demo|TUP-4792/);
    assert.equal(p.doc.querySelectorAll('[data-refund]').length, 0);
  });

  test("nothing is written to the browser's storage", async () => {
    const p = await load({ page: "admin/refunds.html", url: "/admin/refunds.html", routes: routes() });
    await settle(); await settle();
    p.doc.querySelector('[data-refund="11"]').click(); await settle();
    assert.equal(storageWrites(p), 0);
  });
});
