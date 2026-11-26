// Frontend behaviour for the pages changed in this round: canteen ordering switch, staff accounts,
// and password recovery on the student sign-in page. Runs in jsdom with a scripted API.
const { test, describe, afterEach } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const { loadPage, settle, text } = require("./harness");

const ROOT = process.env.FRONTEND_ROOT || path.resolve(__dirname, "../../frontend");
const open = [];
afterEach(() => { while (open.length) { try { open.pop().close(); } catch (_) {} } });
const load = async (opts) => { const p = await loadPage({ root: ROOT, ...opts }); open.push(p); return p; };
const submit = (p, selector) => p.doc.querySelector(selector).dispatchEvent(new p.win.Event("submit", { cancelable: true, bubbles: true }));
const click = (p, selector) => p.doc.querySelector(selector).click();
const calls = (p, method, fragment) => p.calls.filter((c) => c.method === method && c.path.includes(fragment));
const storageWrites = (p) => p.win.localStorage.length + p.win.sessionStorage.length;

// ---------- Canteen settings ----------

const ORDERS_OPEN = { "GET /api/canteen/status": { status: 200, body: { is_accepting_orders: true, message: null } } };

describe("canteen ordering switch", () => {
  test("shows the server's status and no invented name or hours fields", async () => {
    const p = await load({ page: "admin/settings.html", url: "/admin/settings.html", routes: ORDERS_OPEN });
    await settle();
    assert.match(text(p.doc), /Open\. Students can place orders\./);
    assert.equal(p.doc.querySelector('input[name="canteen_name"]'), null);
    assert.equal(p.doc.querySelector('input[type="time"]'), null);
    assert.match(text(p.doc), /not stored in the system yet/);
  });

  test("stopping orders sends the switch and the message, then reloads the status", async () => {
    const p = await load({ page: "admin/settings.html", url: "/admin/settings.html", routes: {
      ...ORDERS_OPEN,
      "PATCH /api/admin/canteen/status": { status: 200, body: { is_accepting_orders: false, message: "Exams" } },
    } });
    await settle();
    p.doc.querySelector('textarea[name="closed_message"]').value = "Exams";
    click(p, "#toggle-ordering");
    await settle(); await settle();
    const patch = calls(p, "PATCH", "/api/admin/canteen/status")[0];
    assert.deepEqual(patch.body, { is_accepting_orders: false, closed_message: "Exams" });
    assert.ok(calls(p, "GET", "/api/canteen/status").length >= 2, "status is reloaded after the change");
  });

  test("a refused change shows the reason and does not claim success", async () => {
    const p = await load({ page: "admin/settings.html", url: "/admin/settings.html", routes: {
      ...ORDERS_OPEN,
      "PATCH /api/admin/canteen/status": { status: 400, body: { success: false, message: "Validation failed.", details: { closed_message: "Must be at most 200 characters." } } },
    } });
    await settle();
    click(p, "#toggle-ordering");
    await settle(); await settle();
    assert.match(text(p.doc), /Must be at most 200 characters\./);
    assert.doesNotMatch(text(p.doc), /Ordering is closed for students/);
  });

  test("nothing is written to the browser's storage", async () => {
    const p = await load({ page: "admin/settings.html", url: "/admin/settings.html", routes: ORDERS_OPEN });
    await settle();
    click(p, "#toggle-ordering");
    await settle();
    assert.equal(storageWrites(p), 0);
  });
});

// ---------- Staff accounts ----------

const STAFF = [
  { id: 1, name: "Admin Person", email: "admin@canteen.edu", role: "ADMIN", is_active: true, created_at: null },
  { id: 2, name: "Ravi Kumar", email: "ravi@canteen.edu", role: "KITCHEN", is_active: true, created_at: null },
];
const staffRoutes = (extra = {}) => ({
  "GET /api/admin/staff": { status: 200, body: { success: true, message: "", data: { staff: STAFF } } },
  "GET /api/auth/me": { status: 200, body: { success: true, message: "", data: { id: 1, name: "Admin Person", email: "admin@canteen.edu", role: "ADMIN" } } },
  ...extra,
});

describe("staff accounts", () => {
  test("lists real accounts, marks you, and shows no invented staff", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", routes: staffRoutes() });
    await settle(); await settle();
    const shown = text(p.doc);
    assert.match(shown, /Ravi Kumar/);
    assert.match(shown, /\(you\)/);
    assert.doesNotMatch(shown, /Neha Kapoor|Priya Nair|Rohan Das/);
    assert.equal(p.doc.querySelector('[data-toggle="1"]').disabled, true, "you cannot deactivate yourself");
    assert.equal(p.doc.querySelector('select[data-role="1"]').disabled, true, "you cannot change your own role");
  });

  test("creating an account sends the details and the chosen role", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", routes: staffRoutes({
      "POST /api/admin/staff": { status: 201, body: { success: true, message: "", data: { id: 3, name: "New Cook", email: "cook@canteen.edu", role: "KITCHEN", is_active: true } } },
    }) });
    await settle(); await settle();
    click(p, "#add-staff");
    p.doc.querySelector('#staff-form input[name="name"]').value = "New Cook";
    p.doc.querySelector('#staff-form input[name="email"]').value = "cook@canteen.edu";
    p.doc.querySelector('#staff-form input[name="password"]').value = "KitchenPass1";
    p.doc.querySelector('#staff-form select[name="role"]').value = "KITCHEN";
    submit(p, "#staff-form");
    await settle(); await settle();
    assert.deepEqual(calls(p, "POST", "/api/admin/staff")[0].body, { name: "New Cook", email: "cook@canteen.edu", password: "KitchenPass1", role: "KITCHEN" });
    assert.match(text(p.doc), /Staff account created/);
  });

  test("a duplicate email from the server is shown, not hidden", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", routes: staffRoutes({
      "POST /api/admin/staff": { status: 409, body: { success: false, message: "An account with this email already exists." } },
    }) });
    await settle(); await settle();
    click(p, "#add-staff");
    p.doc.querySelector('#staff-form input[name="name"]').value = "Dup";
    p.doc.querySelector('#staff-form input[name="email"]').value = "ravi@canteen.edu";
    p.doc.querySelector('#staff-form input[name="password"]').value = "KitchenPass1";
    submit(p, "#staff-form"); await settle(); await settle();
    assert.match(text(p.doc), /An account with this email already exists\./);
  });

  test("changing a role sends one update", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", routes: staffRoutes({
      "PATCH /api/admin/staff/2": { status: 200, body: { success: true, message: "", data: { ...STAFF[1], role: "ADMIN" } } },
    }) });
    await settle(); await settle();
    const select = p.doc.querySelector('select[data-role="2"]');
    select.value = "ADMIN";
    select.dispatchEvent(new p.win.Event("change", { bubbles: true }));
    await settle(); await settle();
    assert.deepEqual(calls(p, "PATCH", "/api/admin/staff/2")[0].body, { role: "ADMIN" });
  });

  test("deactivating sends is_active false, and a refusal from the server is shown", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", routes: staffRoutes({
      "PATCH /api/admin/staff/2": { status: 409, body: { success: false, message: "You cannot remove your own admin access." } },
    }) });
    await settle(); await settle();
    click(p, '[data-toggle="2"]');
    await settle(); await settle();
    assert.deepEqual(calls(p, "PATCH", "/api/admin/staff/2")[0].body, { is_active: false });
    assert.match(text(p.doc), /You cannot remove your own admin access\./);
  });

  test("setting a new password sends it once and says sessions were ended", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", routes: staffRoutes({
      "PATCH /api/admin/staff/2": { status: 200, body: { success: true, message: "", data: STAFF[1] } },
    }) });
    await settle(); await settle();
    click(p, '[data-password="2"]');
    await settle();
    p.doc.querySelector('form[data-password="2"] input[name="password"]').value = "FreshPass2025";
    submit(p, 'form[data-password="2"]');
    await settle(); await settle();
    assert.deepEqual(calls(p, "PATCH", "/api/admin/staff/2")[0].body, { password: "FreshPass2025" });
    assert.match(text(p.doc), /signed out everywhere/);
  });

  test("an unreachable server is reported honestly on load", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", routes: {
      "GET /api/admin/staff": new TypeError("Failed to fetch"),
      "GET /api/auth/me": new TypeError("Failed to fetch"),
    } });
    await settle(); await settle();
    assert.match(text(p.doc), /Could not reach the server/);
    assert.equal(p.doc.querySelectorAll("#staff-body tr").length, 0);
  });

  test("nothing is written to the browser's storage", async () => {
    const p = await load({ page: "admin/staff.html", url: "/admin/staff.html", routes: staffRoutes() });
    await settle(); await settle();
    click(p, "#add-staff");
    assert.equal(storageWrites(p), 0);
  });
});

// ---------- Student password recovery ----------

const recoveryRoutes = (extra = {}) => ({
  "POST /api/forgot/start": { status: 200, body: { success: true, message: "If an account matches that email address, a 6-digit code has been sent.", data: {} } },
  ...extra,
});

describe("student password recovery", () => {
  test("requesting a code sends the email address and moves to the code screen", async () => {
    const p = await load({ page: "student/login.html", url: "/student/login.html", routes: recoveryRoutes() });
    await settle();
    click(p, '[data-view="v-forgot"]');
    p.doc.getElementById("fg-id").value = "Asha@Example.com";
    submit(p, "#f-forgot"); await settle(); await settle();
    assert.deepEqual(calls(p, "POST", "/api/forgot/start")[0].body, { identifier: "asha@example.com" });
    assert.ok(p.doc.getElementById("v-verify").classList.contains("on"));
  });

  test("a mobile number is refused with the server's clear message", async () => {
    const p = await load({ page: "student/login.html", url: "/student/login.html", routes: recoveryRoutes({
      "POST /api/forgot/start": { status: 400, body: { success: false, message: "Password reset by mobile number isn't available yet. Use the email address on your account.", error: { code: "MOBILE_RESET_UNAVAILABLE" } } },
    }) });
    await settle();
    click(p, '[data-view="v-forgot"]');
    p.doc.getElementById("fg-id").value = "98765 43210";
    submit(p, "#f-forgot"); await settle(); await settle();
    assert.match(p.doc.getElementById("fg-msg").textContent, /isn't available yet/);
  });

  test("a rate-limited request shows the wait message as text", async () => {
    const p = await load({ page: "student/login.html", url: "/student/login.html", routes: recoveryRoutes({
      "POST /api/forgot/start": { status: 429, body: { success: false, message: "Too many attempts. Wait a few minutes and try again.", error: { code: "RATE_LIMITED" } } },
    }) });
    await settle();
    click(p, '[data-view="v-forgot"]');
    p.doc.getElementById("fg-id").value = "student@test.com";
    submit(p, "#f-forgot"); await settle(); await settle();
    assert.match(p.doc.getElementById("fg-msg").textContent, /Too many attempts/);
    assert.doesNotMatch(p.doc.getElementById("fg-msg").textContent, /object/);
  });

  test("the emailed code is checked, then a new password is set with the reset token", async () => {
    const p = await load({ page: "student/login.html", url: "/student/login.html", routes: recoveryRoutes({
      "POST /api/forgot/verify": { status: 200, body: { success: true, message: "Code accepted.", data: { resetToken: "reset-token-123" } } },
      "POST /api/forgot/reset": { status: 200, body: { success: true, message: "Password updated.", data: {} } },
    }) });
    await settle();
    click(p, '[data-view="v-forgot"]');
    p.doc.getElementById("fg-id").value = "student@test.com";
    submit(p, "#f-forgot"); await settle(); await settle();

    const digits = [...p.doc.getElementById("otp").children];
    "123456".split("").forEach((d, i) => { digits[i].value = d; });
    p.doc.getElementById("vbtn").click(); await settle(); await settle();
    assert.deepEqual(calls(p, "POST", "/api/forgot/verify")[0].body, { identifier: "student@test.com", otp: "123456" });
    assert.ok(p.doc.getElementById("v-newpw").classList.contains("on"));

    p.doc.getElementById("np1").value = "BrandNew2025";
    p.doc.getElementById("np2").value = "BrandNew2025";
    p.doc.getElementById("np1").dispatchEvent(new p.win.Event("input"));
    p.doc.getElementById("np2").dispatchEvent(new p.win.Event("input"));
    submit(p, "#f-newpw"); await settle(); await settle();
    assert.deepEqual(calls(p, "POST", "/api/forgot/reset")[0].body, { resetToken: "reset-token-123", password: "BrandNew2025" });
    assert.match(text(p.doc), /Password updated\./);
  });

  test("a wrong code shows the server's message and the boxes are cleared", async () => {
    const p = await load({ page: "student/login.html", url: "/student/login.html", routes: recoveryRoutes({
      "POST /api/forgot/verify": { status: 400, body: { success: false, message: "That code isn't right, or it has expired. Check it or request a new code.", error: { code: "CODE_INVALID" } } },
    }) });
    await settle();
    click(p, '[data-view="v-forgot"]');
    p.doc.getElementById("fg-id").value = "student@test.com";
    submit(p, "#f-forgot"); await settle(); await settle();
    [...p.doc.getElementById("otp").children].forEach((box, i) => { box.value = String(i); });
    p.doc.getElementById("vbtn").click(); await settle(); await settle();
    assert.match(p.doc.getElementById("vmsg").textContent, /That code isn't right/);
    assert.ok([...p.doc.getElementById("otp").children].every((box) => box.value === ""));
  });

  test("backup codes are sent to the server as a recovery code", async () => {
    const p = await load({ page: "student/login.html", url: "/student/login.html", routes: recoveryRoutes({
      "POST /api/recovery/code": { status: 200, body: { success: true, message: "Code accepted.", data: { resetToken: "reset-from-code" } } },
    }) });
    await settle();
    click(p, '[data-view="v-alt"]');
    click(p, '[data-view="v-code"]');
    p.doc.getElementById("rc-id").value = "student@test.com";
    p.doc.getElementById("rc-code").value = "ABCD-EFGH-JKLM";
    submit(p, "#f-code"); await settle(); await settle();
    assert.deepEqual(calls(p, "POST", "/api/recovery/code")[0].body, { identifier: "student@test.com", code: "ABCD-EFGH-JKLM" });
    assert.ok(p.doc.getElementById("v-newpw").classList.contains("on"));
  });

  test("support requests show the reference the server returns", async () => {
    const p = await load({ page: "student/login.html", url: "/student/login.html", routes: recoveryRoutes({
      "POST /api/recovery/request": { status: 201, body: { success: true, message: "Request received.", data: { ref: "TRY-ABC23456" } } },
    }) });
    await settle();
    click(p, '[data-view="v-alt"]');
    click(p, '[data-view="v-support"]');
    p.doc.getElementById("sp-name").value = "Asha Rao";
    p.doc.getElementById("sp-id").value = "student@test.com";
    p.doc.getElementById("sp-mail").value = "asha@example.com";
    p.doc.getElementById("sp-reason").value = "I lost my phone and cannot get the code.";
    submit(p, "#f-support"); await settle(); await settle();
    assert.match(text(p.doc), /TRY-ABC23456/);
  });

  test("the trusted-device option is no longer offered", async () => {
    const p = await load({ page: "student/login.html", url: "/student/login.html", routes: recoveryRoutes() });
    await settle();
    assert.equal(p.doc.getElementById("v-device"), null);
    assert.doesNotMatch(text(p.doc), /trusted device/i);
  });
});
