// Admin pages fixed in this round: orders field mapping, reports and overview on live data,
// no invented data on refunds and categories, and no self-password change on staff.
const { test, describe, afterEach } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const { loadPage, settle, text } = require("./harness");

const ROOT = process.env.FRONTEND_ROOT || path.resolve(__dirname, "../../frontend");
const open = [];
afterEach(() => { while (open.length) { try { open.pop().close(); } catch (_) {} } });
const load = async (opts) => { const p = await loadPage({ root: ROOT, ...opts }); open.push(p); return p; };
const storageWrites = (p) => p.win.localStorage.length + p.win.sessionStorage.length;
const calls = (p, fragment) => p.calls.filter((c) => c.path.includes(fragment));

const ME = { "GET /api/auth/me": { status: 200, body: { success: true, message: "", data: { id: 1, name: "Admin", email: "a@x.com", role: "ADMIN" } } } };

describe("orders page reads the server's field names", () => {
  const ORDERS = { "GET /api/admin/orders": { status: 200, body: { success: true, message: "", data: {
    orders: [{ id: 7, order_number: "TUP-7000", order_status: "ready", payment_status: "paid", total_paise: 22500, student: { id: 2, name: "Meera Iyer", email: "m@x.com" } }],
    pagination: { total: 1, page: 1, per_page: 50 },
  } } } };

  test("shows the student name, the rupee amount and the order status", async () => {
    const p = await load({ page: "admin/orders.html", url: "/admin/orders.html", routes: ORDERS });
    await settle(); await settle();
    const shown = text(p.doc);
    assert.match(shown, /Meera Iyer/);
    assert.match(shown, /₹225/);
    assert.match(shown, /ready/);
    assert.doesNotMatch(shown, /Guest/);
  });

  test("the search and status filter match the real fields", async () => {
    const p = await load({ page: "admin/orders.html", url: "/admin/orders.html", routes: ORDERS });
    await settle(); await settle();
    const search = p.doc.getElementById("order-search");
    search.value = "meera";
    search.dispatchEvent(new p.win.Event("input", { bubbles: true }));
    await settle();
    assert.match(text(p.doc), /TUP-7000/);
    search.value = "nobody";
    search.dispatchEvent(new p.win.Event("input", { bubbles: true }));
    await settle();
    assert.doesNotMatch(text(p.doc), /TUP-7000/);
  });

  test("the ?demo=1 address no longer shows invented orders", async () => {
    const p = await load({ page: "admin/orders.html", url: "/admin/orders.html?demo=1", routes: ORDERS });
    await settle(); await settle();
    assert.doesNotMatch(text(p.doc), /Aarav Shah|TUP-4825|Read-only demo data/);
    assert.equal(calls(p, "/api/admin/orders").length, 1, "the real list is requested");
  });
});

describe("reports and overview use live data", () => {
  const OVERVIEW = { total_orders: 10, paid_orders: 8, cancelled_orders: 1, gross_revenue_paise: 50000, refunded_paise: 2000,
    net_revenue_paise: 48000, average_order_value_paise: 6250, completion_rate_percent: 75.0, average_preparation_minutes: null };
  const REPORTS = {
    "GET /api/admin/reports/overview": { status: 200, body: { success: true, message: "", data: OVERVIEW } },
    "GET /api/admin/reports/sales": { status: 200, body: { success: true, message: "", data: { days: [
      { date: "2026-02-10", orders: 4, revenue_paise: 20000, refunded_paise: 0 },
      { date: "2026-02-11", orders: 6, revenue_paise: 30000, refunded_paise: 2000 } ] } } },
    "GET /api/admin/reports/popular-items": { status: 200, body: { success: true, message: "", data: { items: [
      { item_name: "=HYPERLINK(\"x\")", menu_item_id: 5, quantity: 9, revenue_paise: 13500 } ] } } },
    "GET /api/admin/reports/categories": { status: 200, body: { success: true, message: "", data: { categories: [
      { category: "Snacks", quantity: 9, revenue_paise: 13500 } ] } } },
    "GET /api/admin/reports/peak-hours": { status: 200, body: { success: true, message: "", data: { timezone_offset_minutes: 330, hours: [
      { hour: 13, orders: 6 }, { hour: 9, orders: 2 } ] } } },
    "GET /api/admin/reports/orders": { status: 200, body: { success: true, message: "", data: { total: 10,
      by_order_status: { received: 1, collected: 8, cancelled: 1 }, by_payment_status: { paid: 8, pending: 2 } } } },
  };

  test("reports load all six endpoints for one period and show the server's figures", async () => {
    const p = await load({ page: "admin/reports.html", url: "/admin/reports.html", routes: { ...ME, ...REPORTS } });
    await settle(); await settle(); await settle();
    const shown = text(p.doc);
    assert.match(shown, /Gross revenue\s*₹500/);
    assert.match(shown, /Net revenue\s*₹480/);
    assert.match(shown, /Snacks/);
    const reportCalls = p.calls.filter((c) => c.path.includes("/api/admin/reports/"));
    assert.equal(reportCalls.length, 6);
    assert.ok(reportCalls.every((c) => /from=\d{4}-\d{2}-\d{2}&to=\d{4}-\d{2}-\d{2}/.test(c.path)));
    assert.doesNotMatch(shown, /Masala Dosa|TUP-4821/);
  });

  test("the CSV export is built from the sales rows and neutralises spreadsheet formulas", async () => {
    const p = await load({ page: "admin/reports.html", url: "/admin/reports.html", routes: { ...ME, ...REPORTS } });
    await settle(); await settle(); await settle();
    let created = null;
    p.win.URL.createObjectURL = (blob) => { created = blob; return "blob:test"; };
    p.win.URL.revokeObjectURL = () => {};
    [...p.doc.querySelectorAll("button")].find((b) => b.textContent.trim() === "Export sales CSV").click();
    await settle();
    assert.ok(created, "an export is produced");
    const csv = await new Promise((resolve, reject) => {
      const reader = new p.win.FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsText(created);
    });
    assert.match(csv, /Day,Orders,Revenue \(INR\),Refunded \(INR\),Net \(INR\)/);
    assert.match(csv, /2026-02-11,6,300\.00,20\.00,280\.00/);
    assert.equal(p.win.trayUI.csvCell("=HYPERLINK(\"x\")"), "\"'=HYPERLINK(\"\"x\"\")\"");
  });

  test("a reversed date range is refused before any request", async () => {
    const p = await load({ page: "admin/reports.html", url: "/admin/reports.html", routes: { ...ME, ...REPORTS } });
    await settle(); await settle(); await settle();
    const before = p.calls.length;
    p.doc.getElementById("from").value = "2026-03-01";
    p.doc.getElementById("to").value = "2026-02-01";
    [...p.doc.querySelectorAll("button")].find((b) => b.textContent.trim() === "Show").click();
    await settle();
    assert.equal(p.calls.length, before);
    assert.match(text(p.doc), /start date must be on or before/);
  });

  test("the overview shows reporting figures for today and the last 30 days, not paginated orders", async () => {
    const p = await load({ page: "admin/dashboard.html", url: "/admin/dashboard.html", routes: {
      ...ME,
      "GET /api/admin/reports/overview": { status: 200, body: { success: true, message: "", data: OVERVIEW } },
      "GET /api/admin/orders": { status: 200, body: { success: true, message: "", data: { orders: [], pagination: { total: 0 } } } },
    } });
    await settle(); await settle(); await settle();
    assert.match(text(p.doc), /Today/);
    assert.match(text(p.doc), /Last 30 days/);
    assert.match(text(p.doc), /Gross revenue\s*₹500/);
    assert.equal(calls(p, "/api/admin/reports/overview").length, 2);
    assert.equal(calls(p, "payment_status=paid").length, 0, "figures do not come from the paginated list");
  });
});

describe("categories page shows no invented data", () => {
  test("categories shows no invented categories and saves nothing", async () => {
    const p = await load({ page: "admin/categories.html", url: "/admin/categories.html", routes: ME });
    await settle();
    assert.match(text(p.doc), /Not connected to the live system yet/);
    assert.doesNotMatch(text(p.doc), /Breakfast|Desserts/);
    assert.equal(storageWrites(p), 0);
  });
});

describe("staff page", () => {
  test("you cannot set your own password here, because it would sign you out", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", routes: {
      ...ME,
      "GET /api/admin/staff": { status: 200, body: { success: true, message: "", data: { staff: [
        { id: 1, name: "Admin", email: "a@x.com", role: "ADMIN", is_active: true },
        { id: 2, name: "Ravi", email: "r@x.com", role: "KITCHEN", is_active: true } ] } } },
    } });
    await settle(); await settle(); await settle();
    assert.equal(p.doc.querySelector('[data-password="1"]').disabled, true);
    assert.equal(p.doc.querySelector('[data-password="2"]').disabled, false);
  });
});
