// Unit tests for the pure helpers in frontend/shared/admin-panel.js. Run with: node --test tests/frontend/
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// The module attaches itself to window.adminPanel. Pure helpers do not touch the DOM, so a plain
// object is enough to load it.
function loadAdminPanel() {
  const file = path.join(__dirname, "..", "..", "frontend", "shared", "admin-panel.js");
  const sandbox = { window: {}, console, Intl, Date, Math, Number, Array, Object, String, JSON, Promise, Blob: function () {} };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(file, "utf8"), sandbox, { filename: "admin-panel.js" });
  return sandbox.window.adminPanel;
}

const P = loadAdminPanel();

test("money is shown in rupees with two decimals from integer paise", () => {
  assert.equal(P.money(0), "₹0.00");
  assert.equal(P.money(4500), "₹45.00");
  assert.equal(P.money(123456), "₹1,234.56");
  assert.equal(P.money(undefined), "₹0.00");
});

test("typed rupee amounts convert to paise, and anything else is rejected", () => {
  assert.equal(P.rupeesToPaise("75"), 7500);
  assert.equal(P.rupeesToPaise("75.5"), 7550);
  assert.equal(P.rupeesToPaise("1,200"), 120000);
  assert.equal(P.rupeesToPaise("₹ 45.25"), 4525);
  assert.equal(P.rupeesToPaise("45.555"), null);
  assert.equal(P.rupeesToPaise("-5"), null);
  assert.equal(P.rupeesToPaise("abc"), null);
  assert.equal(P.rupeesToPaise(""), null);
});

test("day arithmetic is inclusive and handles month boundaries", () => {
  assert.equal(P.addDays("2026-11-26", -29), "2026-10-28");
  assert.equal(P.addDays("2026-03-01", -1), "2026-02-28");
  assert.equal(P.dayCount("2026-11-26", "2026-11-26"), 1);
  assert.equal(P.dayCount("2026-11-01", "2026-11-30"), 30);
  assert.ok(Number.isNaN(P.dayCount("nope", "2026-11-30")));
});

test("the canteen's current day is a YYYY-MM-DD string", () => {
  assert.match(P.canteenToday(), /^\d{4}-\d{2}-\d{2}$/);
});

test("CSV cells are quoted when needed and formula-like text is neutralised", () => {
  assert.equal(P.csvCell("plain"), "plain");
  assert.equal(P.csvCell('say "hi", now'), '"say ""hi"", now"');
  assert.equal(P.csvCell("=HYPERLINK(\"x\")"), "\"'=HYPERLINK(\"\"x\"\")\"");
  assert.equal(P.csvCell("+1"), "'+1");
  assert.equal(P.csvCell("-2"), "'-2");
  assert.equal(P.csvCell("@cmd"), "'@cmd");
  assert.equal(P.csvCell(null), "");
  assert.equal(P.csvCell(12), "12");
});

test("CSV output starts with a byte-order mark and uses CRLF line endings", () => {
  const text = P.csvText([["a", "b"], ["1", "2,3"]]);
  assert.equal(text.charCodeAt(0), 0xfeff);
  assert.equal(text.slice(1), 'a,b\r\n1,"2,3"\r\n');
});

test("unwrap accepts both the wrapped and the bare response shapes", () => {
  assert.equal(JSON.stringify(P.unwrap({ success: true, data: { a: 1 } })), '{"a":1}');
  assert.equal(JSON.stringify(P.unwrap({ items: [1] })), '{"items":[1]}');
});

test("errors become plain messages and only sessions prompt a sign-in", () => {
  assert.equal(P.describeError({ status: 401 }).signIn, true);
  // A network failure has no HTTP status at all; the API client throws without one.
  assert.equal(P.describeError({ message: "Failed to fetch" }).signIn, false);
  assert.match(P.describeError({ message: "Failed to fetch" }).text, /Could not reach the server/);
  assert.equal(P.describeError({ status: 403 }).text, "Administrator access is required for this page.");
  assert.equal(P.describeError({ status: 429 }).text, "Too many requests. Wait a moment and try again.");
  assert.equal(P.describeError({ status: 409, message: "Already exists." }).text, "Already exists.");
  assert.equal(P.describeError({ status: 503 }).text.includes("Nothing was changed"), true);
  // Missing second factor is completed on the sign-in page, so it routes there.
  assert.equal(P.describeError({ status: 403, code: "MFA_REQUIRED" }).signIn, true);
  assert.equal(P.describeError({ status: 401, code: "MFA_SESSION_EXPIRED" }).signIn, true);
});

test("field details come only from a validation response", () => {
  // Compared as JSON: objects created inside the loaded module come from another realm.
  const json = (value) => JSON.stringify(value);
  assert.equal(json(P.fieldDetails({ data: { details: { name: "Required." } } })), json({ name: "Required." }));
  assert.equal(json(P.fieldDetails({ data: { details: "text" } })), "{}");
  assert.equal(json(P.fieldDetails(undefined)), "{}");
});
