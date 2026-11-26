(function () {
  const CART_KEY = "trayup-cart";
  const SETTINGS_KEY = "trayup-canteen-settings";
  const DEFAULT_SETTINGS = { name: "TrayUP Canteen", open: "08:00", close: "18:00", status: "Open" };
  const MAX_CART_LINES = 50;
  const MAX_QTY = 99;
  const MAX_PRICE = 100000;
  const MAX_NAME_LENGTH = 120;
  const MAX_URL_LENGTH = 2048;
  const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;
  const CONTROL_CHARACTERS = /[\x00-\x1f\x7f]/;
  const STATUSES = ["Open", "Closed"];

  // Stored values are untrusted: anything in localStorage can be edited by the
  // user, by another script on the same origin, or left behind by an older
  // version of the app. Every reader must pass the value through one of these
  // validators before rendering or sending it.

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function cleanText(value, maxLength) {
    if (typeof value !== "string") return null;
    const text = value.trim();
    if (!text || text.length > maxLength || CONTROL_CHARACTERS.test(text)) return null;
    return text;
  }

  // Only http(s) URLs and relative paths are allowed. This rejects javascript:,
  // data:, blob: and any other scheme.
  function safeImageUrl(value) {
    if (typeof value !== "string") return null;
    const url = value.trim();
    if (!url || url.length > MAX_URL_LENGTH) return null;
    try {
      const parsed = new URL(url, window.location.href);
      if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return null;
    } catch (_) {
      return null;
    }
    return url;
  }

  // Items without artwork are allowed. An image that is present must still be safe.
  function optionalImageUrl(value) {
    if (value === undefined || value === null || value === "") return "";
    return safeImageUrl(value);
  }

  function positiveInteger(value) {
    return Number.isSafeInteger(value) && value >= 1 ? value : null;
  }

  function sanitizeCartItem(entry) {
    if (!isPlainObject(entry)) return null;
    const id = positiveInteger(entry.id);
    const name = cleanText(entry.name, MAX_NAME_LENGTH);
    const image = optionalImageUrl(entry.image);
    const qtyValue = positiveInteger(entry.qty);
    const price = typeof entry.price === "number" && Number.isFinite(entry.price) &&
      entry.price >= 0 && entry.price <= MAX_PRICE ? entry.price : null;
    if (id === null || name === null || image === null || qtyValue === null || price === null) return null;
    // Quantities above the limit are clamped so a valid line is never dropped.
    return { id, name, price, image, qty: Math.min(qtyValue, MAX_QTY) };
  }

  // Returns a clean array of cart lines. Invalid lines are dropped and duplicate
  // product ids are merged into the first line. Returns null if the stored value
  // is not an array at all.
  function sanitizeCart(value) {
    if (!Array.isArray(value)) return null;
    const seen = new Set();
    const cart = [];
    value.slice(0, MAX_CART_LINES).forEach((entry) => {
      const item = sanitizeCartItem(entry);
      if (!item || seen.has(item.id)) return;
      seen.add(item.id);
      cart.push(item);
    });
    return cart;
  }

  // Strict: returns null if any field is invalid, so a caller can refuse to save.
  function sanitizeCanteenSettings(value) {
    if (!isPlainObject(value)) return null;
    const name = cleanText(value.name, MAX_NAME_LENGTH);
    const open = typeof value.open === "string" && TIME_PATTERN.test(value.open) ? value.open : null;
    const close = typeof value.close === "string" && TIME_PATTERN.test(value.close) ? value.close : null;
    const status = STATUSES.includes(value.status) ? value.status : null;
    if (name === null || open === null || close === null || status === null) return null;
    return { name, open, close, status };
  }

  function readValue(key, fallback, validate) {
    try {
      const raw = localStorage.getItem(key);
      const parsed = raw ? JSON.parse(raw) : fallback;
      if (!validate) return parsed;
      const checked = validate(parsed);
      return checked === null ? fallback : checked;
    } catch (_) {
      return fallback;
    }
  }

  window.trayStorage = {
    get(key, fallback, validate) {
      return readValue(key, fallback, validate);
    },
    set(key, value) {
      localStorage.setItem(key, JSON.stringify(value));
    },
    remove(key) {
      localStorage.removeItem(key);
    },
    getCart() {
      return readValue(CART_KEY, [], sanitizeCart);
    },
    getCanteenSettings() {
      return readValue(SETTINGS_KEY, { ...DEFAULT_SETTINGS }, sanitizeCanteenSettings);
    },
    validators: {
      cart: sanitizeCart,
      canteenSettings: sanitizeCanteenSettings
    }
  };
})();
