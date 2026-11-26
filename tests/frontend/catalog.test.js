// Run with: node --test tests/frontend/
// Dependency-free: uses Node's built-in test runner.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const catalog = require(path.join(__dirname, "..", "..", "frontend", "shared", "catalog.js"));

const live = [
  catalog.toProduct({ id: 12, name: "Veg Pulao", category: "Lunch", description: "Rice", price_paise: 9000, image_url: null }),
  catalog.toProduct({ id: 34, name: "Cold Coffee", category: "Drinks", description: "Chilled", price_paise: 8000, image_url: "https://example.com/a.jpg" })
];

test("toProduct converts paise to rupees and provides a placeholder image", () => {
  const product = live[0];

  assert.equal(product.price, 90);
  assert.equal(product.isAvailable, true);
  assert.equal(product.image, catalog.PLACEHOLDER_IMAGE);
  assert.equal(live[1].image, "https://example.com/a.jpg");
});

test("a line whose id and name still match is kept, with live price and details", () => {
  const stored = [{ id: 12, name: "Veg Pulao", price: 50, qty: 2, image: "old.jpg" }];

  const { cart, removed } = catalog.reconcileCart(stored, live);

  assert.deepEqual(removed, []);
  assert.equal(cart.length, 1);
  assert.equal(cart[0].price, 90);
  assert.equal(cart[0].qty, 2);
  assert.equal(cart[0].image, catalog.PLACEHOLDER_IMAGE);
});

test("name match ignores case and surrounding spaces", () => {
  const { cart } = catalog.reconcileCart([{ id: 34, name: "  cold COFFEE ", qty: 1 }], live);

  assert.equal(cart.length, 1);
});

test("a stale demo id that now points at a different dish is dropped, never re-priced", () => {
  // Old demo cart: id 12 was "Chicken Biryani". Live id 12 is "Veg Pulao".
  const stored = [{ id: 12, name: "Chicken Biryani", price: 150, qty: 1 }];

  const { cart, removed } = catalog.reconcileCart(stored, live);

  assert.deepEqual(cart, []);
  assert.deepEqual(removed, ["Chicken Biryani"]);
});

test("a dish removed from the menu is dropped and reported", () => {
  const { cart, removed } = catalog.reconcileCart([{ id: 99, name: "Gone Dish", qty: 1 }], live);

  assert.deepEqual(cart, []);
  assert.deepEqual(removed, ["Gone Dish"]);
});

test("a dish renamed by an admin no longer matches and is dropped", () => {
  const stored = [{ id: 34, name: "Iced Coffee", qty: 1 }];

  const { cart, removed } = catalog.reconcileCart(stored, live);

  assert.deepEqual(cart, []);
  assert.deepEqual(removed, ["Iced Coffee"]);
});

test("duplicate lines for one dish are merged and capped at the server limit", () => {
  const stored = [
    { id: 34, name: "Cold Coffee", qty: 15 },
    { id: 34, name: "Cold Coffee", qty: 10 }
  ];

  const { cart, capped } = catalog.reconcileCart(stored, live);

  assert.equal(cart.length, 1);
  assert.equal(cart[0].qty, catalog.MAX_QUANTITY_PER_ITEM);
  assert.deepEqual(capped, ["Cold Coffee"]);
});

test("zero, negative, fractional and non-numeric quantities are dropped", () => {
  const stored = [
    { id: 34, name: "Cold Coffee", qty: 0 },
    { id: 34, name: "Cold Coffee", qty: -2 },
    { id: 12, name: "Veg Pulao", qty: "abc" },
    { id: 12, name: "Veg Pulao", qty: 0.5 }
  ];

  const { cart, removed } = catalog.reconcileCart(stored, live);

  assert.deepEqual(cart, []);
  assert.equal(removed.length, 4);
});

test("a missing or malformed cart reconciles to an empty cart", () => {
  assert.deepEqual(catalog.reconcileCart(undefined, live).cart, []);
  assert.deepEqual(catalog.reconcileCart(null, live).cart, []);
  assert.deepEqual(catalog.reconcileCart({ not: "an array" }, live).cart, []);
});

test("an empty live menu removes every line, so nothing can be checked out at a stale price", () => {
  const { cart } = catalog.reconcileCart([{ id: 12, name: "Veg Pulao", qty: 1 }], []);

  assert.deepEqual(cart, []);
});
