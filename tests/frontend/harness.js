// Loads a frontend page with its real scripts into jsdom, with a scripted API.
const { JSDOM, VirtualConsole } = require("jsdom");
const fs = require("fs");
const path = require("path");

const wait = (ms = 15) => new Promise((r) => setTimeout(r, ms));
const settle = async () => { for (let i = 0; i < 6; i++) await wait(); };

// routes: { "GET /api/admin/orders": { status, body } | fn(req) | throws }
async function loadPage({ root, page, url, routes = {}, confirmAnswer = true, local = {}, session = {} }) {
  const pageFile = path.join(root, page);
  const html = fs.readFileSync(pageFile, "utf8");
  const navigations = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => { if (/navigation/i.test(e.message)) navigations.push(e.message); });

  const dom = new JSDOM(html, {
    url: "http://localhost" + url,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole: vc,
  });
  const win = dom.window;
  const calls = [];
  win.confirm = () => confirmAnswer;
  win.alert = () => {};
  win.prompt = () => null;
  win.matchMedia = win.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  win.IntersectionObserver = win.IntersectionObserver || class { observe() {} unobserve() {} disconnect() {} };

  for (const [k, v] of Object.entries(local)) win.localStorage.setItem(k, v);
  for (const [k, v] of Object.entries(session)) win.sessionStorage.setItem(k, v);

  // Like the real server: every page can fetch a CSRF token first.
  const defaults = { "GET /api/csrf-token": { status: 200, body: { csrf_token: "test-csrf" } } };
  win.fetch = async (input, init = {}) => {
    const method = (init.method || "GET").toUpperCase();
    const pathname = String(input).replace(/^https?:\/\/[^/]+/, "");
    const body = init.body ? JSON.parse(init.body) : undefined;
    calls.push({ method, path: pathname, body, headers: init.headers || {} });
    // Yield to the timer queue so runaway loops can't starve the test, and cap them.
    await new Promise((r) => setImmediate(r));
    if (calls.length > 60) { win.__runaway = true; throw new Error("harness: request loop stopped after 60 calls"); }
    const key = `${method} ${pathname}`;
    const bare = pathname.split("?")[0];
    let route = routes[key] ?? routes[`${method} ${bare}`] ?? routes[pathname] ?? routes[bare] ?? defaults[key];
    if (route === undefined) route = { status: 500, body: { success: false, message: "unscripted " + key } };
    if (typeof route === "function") route = await route({ method, path: pathname, body });
    if (route instanceof Error) throw route;
    const status = route.status ?? 200;
    const json = route.body ?? {};
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => json,
    };
  };

  // Run the page's own classic scripts in order, exactly as a browser would.
  const pageDir = path.dirname(pageFile);
  for (const s of [...win.document.querySelectorAll("script[src]")]) {
    const src = s.getAttribute("src");
    if (/^https?:/.test(src)) continue;
    const file = path.resolve(pageDir, src.split("?")[0]);
    win.eval(fs.readFileSync(file, "utf8"));
  }
  await settle();
  return { win, doc: win.document, calls, navigations, runaway: () => !!win.__runaway, close: () => win.close() };
}

const text = (doc) => doc.body.textContent.replace(/\s+/g, " ").trim();

module.exports = { loadPage, settle, text, wait };
