// Production is the default. Demo mode is a labelled sandbox for the staff pages only.
//
// - It starts only when someone clicks "Open demo" on a staff sign-in page.
// - It lasts for this browser tab (sessionStorage) and only on /admin/ and /kitchen/ pages.
// - While it is active, api.js refuses every request, so demo pages cannot read or change real data.
// - Demo data is stored under its own prefix in tab storage, never under the real keys.
// - A failed sign-in never turns demo mode on.
(function () {
  "use strict";

  const MODE_KEY = "trayup-mode";
  const DEMO_PREFIX = "trayup-demo:";
  const STAFF_PAGES = /\/(admin|kitchen)\//;
  const SIGN_IN_PAGES = /\/(admin|kitchen)\/login(\.html)?\/?$/;
  // Keys written by earlier versions. They could make a browser look signed in or hold invented data.
  const LEGACY_KEYS = [
    "trayup-demo-role",
    "trayup-admin-menu",
    "trayup-admin-categories",
    "trayup-admin-staff",
    "trayup-canteen-settings"
  ];

  function readFlag() {
    try { return sessionStorage.getItem(MODE_KEY) === "demo"; } catch (_) { return false; }
  }

  function writeFlag(on) {
    try {
      if (on) sessionStorage.setItem(MODE_KEY, "demo");
      else sessionStorage.removeItem(MODE_KEY);
    } catch (_) {}
  }

  const path = window.location.pathname;
  // Opening a sign-in page always leaves demo mode, so a real sign-in is never blocked by it.
  if (SIGN_IN_PAGES.test(path)) writeFlag(false);
  const demo = STAFF_PAGES.test(path) && !SIGN_IN_PAGES.test(path) && readFlag();

  LEGACY_KEYS.forEach((key) => { try { localStorage.removeItem(key); } catch (_) {} });

  // In demo mode, the storage helper writes to tab storage under a separate prefix.
  if (demo && window.trayStorage) {
    window.trayStorage = {
      get(key, fallback) {
        try {
          const value = sessionStorage.getItem(DEMO_PREFIX + key);
          return value ? JSON.parse(value) : fallback;
        } catch (_) { return fallback; }
      },
      set(key, value) { sessionStorage.setItem(DEMO_PREFIX + key, JSON.stringify(value)); },
      remove(key) { sessionStorage.removeItem(DEMO_PREFIX + key); }
    };
  }

  function escapeText(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
    })[c]);
  }

  function renderBanner() {
    if (!demo) return;
    document.title = "DEMO · " + document.title;
    const bar = document.createElement("div");
    bar.setAttribute("role", "status");
    bar.style.cssText = "position:sticky;top:0;z-index:1000;background:#7a3e00;color:#fff;" +
      "padding:8px 14px;font:600 13px/1.4 system-ui,sans-serif;display:flex;gap:12px;" +
      "align-items:center;justify-content:space-between;flex-wrap:wrap";
    const label = document.createElement("span");
    label.textContent = "DEMO MODE · Sample data only. Nothing here is saved or sent to the canteen.";
    const exit = document.createElement("button");
    exit.type = "button";
    exit.textContent = "Exit demo";
    exit.style.cssText = "background:#fff;color:#7a3e00;border:0;border-radius:6px;padding:6px 12px;font-weight:700;cursor:pointer";
    exit.addEventListener("click", () => {
      writeFlag(false);
      window.location.href = "./login.html";
    });
    bar.append(label, exit);
    document.body.prepend(bar);
  }

  window.trayMode = {
    isDemo() { return demo; },

    // Called only by an explicit "Open demo" button on a staff sign-in page.
    enterDemo() { writeFlag(true); },
    exitDemo() { writeFlag(false); },

    // Shown in production in place of sections that are not yet connected to the server.
    // Nothing is displayed as if it were live data.
    notConnected(selector, heading, message) {
      const target = document.querySelector(selector);
      if (!target) return;
      target.innerHTML =
        `<h1 class="admin-title">${escapeText(heading)}</h1>` +
        `<div class="card" style="margin-top:22px;padding:24px">` +
        `<strong>Not connected to the live system yet.</strong>` +
        `<p style="color:var(--muted);margin-top:8px">${escapeText(message)}</p>` +
        `<p style="color:var(--muted);margin-top:8px">Nothing on this page is saved.</p>` +
        `</div>`;
    }
  };

  if (document.body) renderBanner();
  else document.addEventListener("DOMContentLoaded", renderBanner);
})();
