// Admin management pages: menu, categories, staff, reports, settings. Production uses the real API;
// demo mode shows a notice and makes no requests.
const { test, describe, afterEach } = require("node:test");
const assert = require("node:assert/strict");
const { loadPage, settle, text } = require("./harness");
const path = require("path");

const ROOT = process.env.FRONTEND_ROOT || path.resolve(__dirname, "../../frontend");
const STAFF_SESSION = { "trayup-mode": "demo" };
const toast = (doc) => (doc.querySelector(".toast") || { textContent: "" }).textContent;
const button = (doc, label) => [...doc.querySelectorAll("button")].find((b) => b.textContent.trim() === label);
const submit = (p, selector) => p.doc.querySelector(selector).dispatchEvent(new p.win.Event("submit", { cancelable: true, bubbles: true }));
const count = (calls, method, fragment) => calls.filter((c) => c.method === method && c.path.includes(fragment)).length;
const open = [];
afterEach(() => { while (open.length) { try { open.pop().close(); } catch (_) {} } });
const load = async (opts) => { const p = await loadPage({ root: ROOT, ...opts }); open.push(p); return p; };

const ME = { "GET /api/auth/me": { status: 200, body: { success: true, data: { id: 1, name: "Admin", email: "admin@x.com", role: "ADMIN" } } } };
const CATEGORIES = [
  { id: 1, name: "Snacks", sort_order: 0, item_count: 2 },
  { id: 2, name: "Drinks", sort_order: 10, item_count: 0 },
];
const MENU = [
  { id: 5, name: "Samosa", category: "Snacks", description: "Crisp", price_paise: 1500, image_url: null, is_available: true, stock_quantity: null, reserved_quantity: 0, available_quantity: null },
  { id: 6, name: "Tea", category: "Drinks", description: null, price_paise: 1000, image_url: null, is_available: false, stock_quantity: 10, reserved_quantity: 2, available_quantity: 8 },
];

describe("menu management (production)", () => {
  const routes = (extra = {}) => ({
    "GET /api/admin/menu": { status: 200, body: { success: true, data: {}, items: MENU } },
    "GET /api/admin/categories": { status: 200, body: { success: true, data: {}, categories: CATEGORIES } },
    ...extra,
  });

  test("lists real items with prices in rupees and shows hidden items as hidden", async () => {
    const p = await load({ page: "admin/menu.html", url: "/admin/menu.html", routes: routes() });
    await settle();
    const shown = text(p.doc);
    assert.match(shown, /Samosa/);
    assert.match(shown, /₹15/);
    assert.match(shown, /Hidden from students/);
    assert.doesNotMatch(shown, /Masala Dosa/);
    assert.equal(p.win.localStorage.getItem("trayup-admin-menu"), null);
  });

  test("adding an item sends the price in paise and the chosen category", async () => {
    const p = await load({ page: "admin/menu.html", url: "/admin/menu.html", routes: routes({ "POST /api/admin/menu": { status: 201, body: { success: true, data: {}, item: MENU[0] } } }) });
    await settle();
    button(p.doc, "Add item").click(); await settle();
    p.doc.querySelector('input[name="name"]').value = "Paneer Roll";
    p.doc.querySelector('select[name="category"]').value = "Snacks";
    p.doc.querySelector('input[name="price"]').value = "75.50";
    submit(p, "#item-form"); await settle(); await settle();
    const post = p.calls.find((c) => c.method === "POST" && c.path.endsWith("/api/admin/menu"));
    assert.ok(post, "a create request must be sent");
    assert.deepEqual({ name: post.body.name, category: post.body.category, price_paise: post.body.price_paise, stock_quantity: post.body.stock_quantity },
      { name: "Paneer Roll", category: "Snacks", price_paise: 7550, stock_quantity: null });
    assert.match(toast(p.doc), /Menu item added/);
  });

  test("a price that is not a valid amount is caught on the form, and nothing is sent", async () => {
    const p = await load({ page: "admin/menu.html", url: "/admin/menu.html", routes: routes() });
    await settle();
    button(p.doc, "Add item").click(); await settle();
    p.doc.querySelector('input[name="name"]').value = "Bad";
    p.doc.querySelector('select[name="category"]').value = "Snacks";
    p.doc.querySelector('input[name="price"]').value = "seventy";
    submit(p, "#item-form"); await settle();
    assert.equal(count(p.calls, "POST", "/api/admin/menu"), 0);
    assert.match(text(p.doc), /Enter an amount such as 75/);
  });

  test("the server's per-field message is shown on the form", async () => {
    const p = await load({ page: "admin/menu.html", url: "/admin/menu.html", routes: routes({ "POST /api/admin/menu": { status: 400, body: { success: false, message: "Validation failed.", details: { category: "Unknown category. Add it under Categories first." } } } }) });
    await settle();
    button(p.doc, "Add item").click(); await settle();
    p.doc.querySelector('input[name="name"]').value = "Odd";
    p.doc.querySelector('select[name="category"]').value = "Snacks";
    p.doc.querySelector('input[name="price"]').value = "20";
    submit(p, "#item-form"); await settle(); await settle();
    assert.match(text(p.doc), /Unknown category\. Add it under Categories first\./);
  });

  test("showing or hiding an item sends one update, and the menu has no delete control", async () => {
    const p = await load({ page: "admin/menu.html", url: "/admin/menu.html", routes: routes({ "PATCH /api/admin/menu/6": { status: 200, body: { success: true, data: {}, item: MENU[1] } } }) });
    await settle();
    p.doc.querySelector('[data-toggle="6"]').click(); await settle(); await settle();
    const patch = p.calls.find((c) => c.method === "PATCH");
    assert.deepEqual(patch.body, { is_available: true });
    assert.equal(button(p.doc, "Delete"), undefined);
  });

  test("demo mode shows a notice and sends no requests", async () => {
    const p = await load({ page: "admin/menu.html", url: "/admin/menu.html", session: STAFF_SESSION, routes: routes() });
    await settle();
    assert.match(text(p.doc), /Demo mode/);
    assert.doesNotMatch(text(p.doc), /Masala Dosa|Samosa/);
    assert.equal(p.calls.length, 0);
  });
});

describe("menu categories (production)", () => {
  const routes = (extra = {}) => ({
    "GET /api/admin/categories": { status: 200, body: { success: true, data: {}, categories: CATEGORIES } },
    ...extra,
  });

  test("lists categories with item counts and blocks deleting a category that has items", async () => {
    const p = await load({ page: "admin/categories.html", url: "/admin/categories.html", routes: routes() });
    await settle();
    assert.match(text(p.doc), /Snacks/);
    const deleteSnacks = p.doc.querySelector('[data-remove="1"]');
    const deleteDrinks = p.doc.querySelector('[data-remove="2"]');
    assert.equal(deleteSnacks.disabled, true);
    assert.equal(deleteDrinks.disabled, false);
  });

  test("adding a category sends its name and display order", async () => {
    const p = await load({ page: "admin/categories.html", url: "/admin/categories.html", routes: routes({ "POST /api/admin/categories": { status: 201, body: { success: true, data: {}, category: { id: 3, name: "Hot Drinks" } } } }) });
    await settle();
    p.doc.querySelector('#add-form input[name="name"]').value = "Hot Drinks";
    p.doc.querySelector('#add-form input[name="sort_order"]').value = "20";
    submit(p, "#add-form"); await settle(); await settle();
    const post = p.calls.find((c) => c.method === "POST");
    assert.deepEqual(post.body, { name: "Hot Drinks", sort_order: 20 });
  });

  test("a duplicate name from the server is shown next to the form", async () => {
    const p = await load({ page: "admin/categories.html", url: "/admin/categories.html", routes: routes({ "POST /api/admin/categories": { status: 409, body: { success: false, message: "A category with this name already exists.", error: { code: "CATEGORY_NAME_TAKEN" } } } }) });
    await settle();
    p.doc.querySelector('#add-form input[name="name"]').value = "snacks";
    submit(p, "#add-form"); await settle(); await settle();
    assert.match(text(p.doc), /A category with this name already exists\./);
  });

  test("the display order is saved with one update", async () => {
    const p = await load({ page: "admin/categories.html", url: "/admin/categories.html", routes: routes({ "PATCH /api/admin/categories/2": { status: 200, body: { success: true, data: {}, category: CATEGORIES[1] } } }) });
    await settle();
    const input = p.doc.querySelector('[data-order="2"]');
    input.value = "5";
    input.dispatchEvent(new p.win.Event("change", { bubbles: true }));
    await settle(); await settle();
    const patch = p.calls.find((c) => c.method === "PATCH");
    assert.deepEqual(patch.body, { sort_order: 5 });
  });

  test("deleting a category confirms first, then sends one delete request", async () => {
    const p = await load({ page: "admin/categories.html", url: "/admin/categories.html", confirmAnswer: true, routes: routes({ "DELETE /api/admin/categories/2": { status: 200, body: { success: true, data: {} } } }) });
    await settle();
    p.doc.querySelector('[data-remove="2"]').click(); await settle(); await settle();
    assert.equal(count(p.calls, "DELETE", "/api/admin/categories/2"), 1);
  });

  test("renaming sends the new name", async () => {
    const p = await load({ page: "admin/categories.html", url: "/admin/categories.html", routes: routes({ "PATCH /api/admin/categories/1": { status: 200, body: { success: true, data: {}, category: { ...CATEGORIES[0], name: "Quick Bites" } } } }) });
    await settle();
    p.doc.querySelector('[data-rename="1"]').click(); await settle();
    const input = p.doc.querySelector('form[data-rename="1"] input[name="name"]');
    input.value = "Quick Bites";
    submit(p, 'form[data-rename="1"]'); await settle(); await settle();
    assert.deepEqual(p.calls.find((c) => c.method === "PATCH").body, { name: "Quick Bites" });
  });

  test("demo mode shows a notice and sends no requests", async () => {
    const p = await load({ page: "admin/categories.html", url: "/admin/categories.html", session: STAFF_SESSION, routes: routes() });
    await settle();
    assert.match(text(p.doc), /Demo mode/);
    assert.equal(p.calls.length, 0);
  });
});

describe("staff accounts (production)", () => {
  const STAFF = [
    { id: 1, name: "Admin", email: "admin@x.com", role: "ADMIN", is_active: true, created_at: null },
    { id: 2, name: "Ravi", email: "ravi@x.com", role: "KITCHEN", is_active: true, created_at: null },
  ];
  const routes = (extra = {}) => ({
    ...ME,
    "GET /api/admin/staff": { status: 200, body: { success: true, data: {}, staff: STAFF } },
    ...extra,
  });

  test("lists staff, marks your own account, and disables changing it", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", routes: routes() });
    await settle(); await settle();
    assert.match(text(p.doc), /Ravi/);
    assert.match(text(p.doc), /\(you\)/);
    assert.equal(p.doc.querySelector('[data-toggle="1"]').disabled, true);
    assert.equal(p.doc.querySelector('select[data-role="1"]').disabled, true);
    assert.equal(p.doc.querySelector('[data-toggle="2"]').disabled, false);
  });

  test("creating an account sends the role and shows the server's duplicate-email message", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", routes: routes({ "POST /api/admin/staff": { status: 409, body: { success: false, message: "An account with this email already exists.", error: { code: "EMAIL_UNAVAILABLE" } } } }) });
    await settle(); await settle();
    p.doc.querySelector('#staff-form input[name="name"]').value = "New";
    p.doc.querySelector('#staff-form input[name="email"]').value = "ravi@x.com";
    p.doc.querySelector('#staff-form input[name="password"]').value = "KitchenPass1";
    p.doc.querySelector('#staff-form select[name="role"]').value = "ADMIN";
    submit(p, "#staff-form"); await settle(); await settle();
    const post = p.calls.find((c) => c.method === "POST");
    assert.equal(post.body.role, "ADMIN");
    assert.match(text(p.doc), /An account with this email already exists\./);
  });

  test("changing a role sends one update", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", routes: routes({ "PATCH /api/admin/staff/2": { status: 200, body: { success: true, data: {}, staff: { ...STAFF[1], role: "ADMIN" } } } }) });
    await settle(); await settle();
    const select = p.doc.querySelector('select[data-role="2"]');
    select.value = "ADMIN";
    select.dispatchEvent(new p.win.Event("change", { bubbles: true }));
    await settle(); await settle();
    assert.deepEqual(p.calls.find((c) => c.method === "PATCH").body, { role: "ADMIN" });
  });

  test("deactivating sends is_active false and a server refusal is shown", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", routes: routes({ "PATCH /api/admin/staff/2": { status: 409, body: { success: false, message: "At least one active administrator must remain.", error: { code: "LAST_ADMIN" } } } }) });
    await settle(); await settle();
    p.doc.querySelector('[data-toggle="2"]').click(); await settle(); await settle();
    assert.deepEqual(p.calls.find((c) => c.method === "PATCH").body, { is_active: false });
    assert.match(text(p.doc), /At least one active administrator must remain\./);
  });

  test("demo mode shows a notice and sends no requests", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", session: STAFF_SESSION, routes: routes() });
    await settle();
    assert.match(text(p.doc), /Demo mode/);
    assert.equal(p.calls.length, 0);
  });
});

describe("reports (production)", () => {
  const OVERVIEW = { total_orders: 10, paid_orders: 8, cancelled_orders: 1, gross_revenue_paise: 50000, refunded_paise: 2000, net_revenue_paise: 48000, average_order_value_paise: 6250, completion_rate_percent: 75, average_preparation_minutes: 11 };
  const routes = (extra = {}) => ({
    "GET /api/admin/reports/overview": { status: 200, body: { success: true, data: OVERVIEW } },
    "GET /api/admin/reports/sales": { status: 200, body: { success: true, data: { days: [
      { date: "2026-11-24", orders: 4, revenue_paise: 20000, refunded_paise: 0 },
      { date: "2026-11-25", orders: 6, revenue_paise: 30000, refunded_paise: 2000 },
    ] } } },
    "GET /api/admin/reports/popular-items": { status: 200, body: { success: true, data: { items: [{ menu_item_id: 5, item_name: "=HYPERLINK(\"x\")", quantity: 9, revenue_paise: 13500 }] } } },
    "GET /api/admin/reports/categories": { status: 200, body: { success: true, data: { categories: [{ category: "Snacks", quantity: 9, revenue_paise: 13500 }] } } },
    "GET /api/admin/reports/peak-hours": { status: 200, body: { success: true, data: { timezone_offset_minutes: 330, hours: [{ hour: 13, orders: 6 }, { hour: 9, orders: 2 }, ...Array.from({ length: 22 }, (_, i) => ({ hour: i + (i >= 9 ? 2 : 0), orders: 0 })).slice(0, 22)].slice(0, 24) } } },
    "GET /api/admin/reports/orders": { status: 200, body: { success: true, data: { total: 10, by_order_status: { received: 1, collected: 8, cancelled: 1 }, by_payment_status: { paid: 8, pending: 2 } } } },
    ...extra,
  });

  test("shows real figures for the period and loads all six reports with the same dates", async () => {
    const p = await load({ page: "admin/reports.html", url: "/admin/reports.html", routes: routes() });
    await settle(); await settle();
    const shown = text(p.doc);
    assert.match(shown, /Gross revenue\s*₹500/);
    assert.match(shown, /Net revenue\s*₹480/);
    assert.match(shown, /Sales by day/);
    assert.doesNotMatch(shown, /TUP-4821|Masala Dosa/);
    const reportCalls = p.calls.filter((c) => c.path.includes("/api/admin/reports/"));
    assert.equal(reportCalls.length, 6);
    assert.ok(reportCalls.every((c) => /from=\d{4}-\d{2}-\d{2}&to=\d{4}-\d{2}-\d{2}/.test(c.path)));
  });

  test("a range that starts after it ends is refused without a request", async () => {
    const p = await load({ page: "admin/reports.html", url: "/admin/reports.html", routes: routes() });
    await settle(); await settle();
    const before = p.calls.length;
    p.doc.querySelector("#from").value = "2026-12-01";
    p.doc.querySelector("#to").value = "2026-11-01";
    button(p.doc, "Show").click(); await settle();
    assert.equal(p.calls.length, before);
    assert.match(text(p.doc), /start date must be on or before/);
  });

  test("a failed report shows the reason and no figures", async () => {
    const p = await load({ page: "admin/reports.html", url: "/admin/reports.html", routes: routes({ "GET /api/admin/reports/overview": { status: 500, body: { success: false, message: "boom" } } }) });
    await settle(); await settle();
    assert.doesNotMatch(text(p.doc), /Gross revenue/);
    assert.match(text(p.doc), /Something went wrong|boom|Nothing was changed/);
  });

  test("the CSV export contains the sales rows and neutralises spreadsheet formulas", async () => {
    const p = await load({ page: "admin/reports.html", url: "/admin/reports.html", routes: routes() });
    await settle(); await settle();
    let created = null;
    p.win.URL.createObjectURL = (blob) => { created = blob; return "blob:test"; };
    p.win.URL.revokeObjectURL = () => {};
    button(p.doc, "Export sales CSV").click();
    await settle();
    assert.ok(created, "an export must be produced");
    const csv = await new Promise((resolve, reject) => {
      const reader = new p.win.FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsText(created);
    });
    assert.match(csv, /^\uFEFF?Day,Orders,Revenue \(INR\),Refunded \(INR\),Net \(INR\)/);
    assert.match(csv, /2026-11-25,6,300\.00,20\.00,280\.00/);
    assert.equal(p.win.trayUI.csvCell("=HYPERLINK(\"x\")"), "\"'=HYPERLINK(\"\"x\"\")\"");
    assert.equal(p.win.trayUI.csvCell(-5), "-5");
  });

  test("demo mode shows a notice and sends no requests", async () => {
    const p = await load({ page: "admin/reports.html", url: "/admin/reports.html", session: STAFF_SESSION, routes: routes() });
    await settle();
    assert.match(text(p.doc), /Demo mode/);
    assert.equal(p.calls.length, 0);
  });
});

describe("canteen settings (production)", () => {
  const SETTINGS = { is_accepting_orders: true, message: null, canteen_name: "Main Canteen", opens_at: "08:00", closes_at: "18:00", closed_message: null };
  const routes = (extra = {}) => ({
    "GET /api/admin/canteen/settings": { status: 200, body: { ...SETTINGS } },
    ...extra,
  });

  test("shows the saved name, hours and ordering state", async () => {
    const p = await load({ page: "admin/settings.html", url: "/admin/settings.html", routes: routes() });
    await settle();
    assert.equal(p.doc.querySelector('input[name="canteen_name"]').value, "Main Canteen");
    assert.equal(p.doc.querySelector('input[name="opens_at"]').value, "08:00");
    assert.match(text(p.doc), /Students can place orders right now/);
  });

  test("saving name and hours sends the three fields", async () => {
    const p = await load({ page: "admin/settings.html", url: "/admin/settings.html", routes: routes({ "PATCH /api/admin/canteen/settings": { status: 200, body: { ...SETTINGS, canteen_name: "North" } } }) });
    await settle();
    p.doc.querySelector('input[name="canteen_name"]').value = "North";
    submit(p, "#details-form"); await settle(); await settle();
    assert.deepEqual(p.calls.find((c) => c.method === "PATCH").body, { canteen_name: "North", opens_at: "08:00", closes_at: "18:00" });
  });

  test("closing time before opening time is shown next to the closing field", async () => {
    const p = await load({ page: "admin/settings.html", url: "/admin/settings.html", routes: routes({ "PATCH /api/admin/canteen/settings": { status: 400, body: { success: false, message: "Validation failed.", details: { closes_at: "Closing time must be after opening time." } } } }) });
    await settle();
    submit(p, "#details-form"); await settle(); await settle();
    assert.match(text(p.doc), /Closing time must be after opening time\./);
  });

  test("stopping orders sends the switch with a message, then reloads the full settings", async () => {
    const p = await load({ page: "admin/settings.html", url: "/admin/settings.html", routes: routes({ "PATCH /api/admin/canteen/status": { status: 200, body: { is_accepting_orders: false, message: "Exams" } } }) });
    await settle();
    p.doc.querySelector('input[name="closed_message"]').value = "Exams";
    button(p.doc, "Stop taking orders").click(); await settle(); await settle();
    const patch = p.calls.find((c) => c.method === "PATCH" && c.path.includes("/canteen/status"));
    assert.deepEqual(patch.body, { is_accepting_orders: false, closed_message: "Exams" });
    assert.ok(p.calls.some((c) => c.method === "GET" && c.path.includes("/canteen/settings")));
  });

  test("demo mode shows a notice and sends no requests", async () => {
    const p = await load({ page: "admin/settings.html", url: "/admin/settings.html", session: STAFF_SESSION, routes: routes() });
    await settle();
    assert.match(text(p.doc), /Demo mode/);
    assert.equal(p.calls.length, 0);
  });
});
