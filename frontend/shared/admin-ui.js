// Shared helpers for the admin management pages: DOM building, money and dates, honest error text,
// the demo-only notice and CSV export. Nothing here calls the server.
(function () {
  "use strict";

  const CANTEEN_TZ = "Asia/Kolkata";

  const STYLE = `
    .ui-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
    .ui-form { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); align-items: end; }
    .ui-field { display: grid; gap: 6px; font-size: 13px; color: var(--muted); }
    .ui-field input, .ui-field select, .ui-field textarea { font: inherit; color: inherit; height: 40px; border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; background: #fff; }
    .ui-field textarea { height: auto; min-height: 72px; }
    .ui-field .ui-hint { font-size: 12px; }
    .ui-field .ui-error { color: #9b1c1c; font-size: 12px; }
    .ui-row-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .ui-row-actions .btn { padding: 6px 10px; font-size: 13px; }
    .ui-bar { height: 10px; background: var(--brand, #2d6a4f); border-radius: 4px; }
    .ui-muted { color: var(--muted); }
    .ui-num { text-align: right; font-variant-numeric: tabular-nums; }
    .ui-toolbar { display: flex; gap: 12px; flex-wrap: wrap; align-items: end; margin: 18px 0; }
    .ui-section { margin-top: 26px; }
    .ui-section h2 { font-size: 18px; margin: 0 0 10px; }
  `;

  (function injectStyle() {
    if (document.getElementById("ui-admin-style")) return;
    const style = document.createElement("style");
    style.id = "ui-admin-style";
    style.textContent = STYLE;
    document.head.appendChild(style);
  })();

  function el(tag, props, children) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([key, value]) => {
      if (value === undefined || value === null || value === false) return;
      if (key === "text") node.textContent = value;
      else if (key === "class") node.className = value;
      else if (key === "style") node.style.cssText = value;
      else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
      else if (key === "dataset") Object.entries(value).forEach(([k, v]) => { node.dataset[k] = v; });
      else node.setAttribute(key, value === true ? "" : String(value));
    });
    (children || []).forEach((child) => {
      if (child === undefined || child === null || child === false) return;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return node;
  }

  // Money is stored in paise (integers). Display converts once, here.
  function money(paise) {
    const rupees = Number(paise || 0) / 100;
    return "₹" + rupees.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }

  // Parses what a person types ("75", "75.5", "1,200") into paise. Returns null when it is not a valid amount.
  function rupeesToPaise(text) {
    const cleaned = String(text ?? "").replace(/[₹,\s]/g, "");
    if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
    return Math.round(Number(cleaned) * 100);
  }

  function isoDay(date) {
    return date.toISOString().slice(0, 10);
  }

  function canteenToday() {
    return new Date().toLocaleDateString("en-CA", { timeZone: CANTEEN_TZ });
  }

  function addDays(day, delta) {
    const date = new Date(day + "T00:00:00Z");
    date.setUTCDate(date.getUTCDate() + delta);
    return isoDay(date);
  }

  function formatDay(day) {
    const date = new Date(day + "T00:00:00Z");
    return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  }

  function formatTime(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return String(iso);
    return date.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: CANTEEN_TZ });
  }

  // Turns an error from the API client into text a staff member can act on. Never invents data.
  function describeError(error) {
    if (error && error.code === "DEMO_MODE") return { signIn: false, text: "Demo mode does not contact the server." };
    if (error && (error.status === 401 || error.status === 403)) {
      return { signIn: true, text: error.status === 401 ? "Your session has ended. Sign in again to continue." : "Administrator access is required for this section." };
    }
    if (error && typeof error.status !== "number") {
      return { signIn: false, text: "Could not reach the server. Check the connection and try again. Nothing was changed." };
    }
    return { signIn: false, text: (error && error.message) || "Something went wrong. Nothing was changed." };
  }

  function fieldErrors(error) {
    const details = error && error.data && error.data.details;
    return details && typeof details === "object" ? details : {};
  }

  function notice(text, tone) {
    return el("div", { class: "card" + (tone === "warning" ? " status warning" : tone === "danger" ? " status danger" : ""), style: "padding:14px 16px;margin:14px 0" }, [text]);
  }

  function errorNotice(error) {
    const described = describeError(error);
    const children = [described.text];
    if (described.signIn) {
      children.push(" ");
      children.push(el("a", { href: "./login.html", style: "text-decoration:underline" }, ["Sign in"]));
    }
    return el("div", { class: "card status danger", style: "padding:14px 16px;margin:14px 0" }, children);
  }

  function header(title, actions) {
    return el("div", { style: "display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap" }, [
      el("h1", { class: "admin-title", text: title }),
      actions || null
    ]);
  }

  // In demo mode these sections do not load live data, and nothing here is editable.
  function demoOnly(root, heading, message) {
    root.replaceChildren(
      header(heading),
      notice(`Demo mode. ${message} Exit demo and sign in to use this section.`, "warning")
    );
  }

  function csvCell(value) {
    // Text that starts with a formula character would run as a formula in a spreadsheet, so prefix it.
    let text = value === null || value === undefined ? "" : String(value);
    if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function downloadCsv(filename, rows) {
    const body = rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
    const blob = new Blob(["\ufeff" + body + "\r\n"], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = el("a", { href: url, download: filename });
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function table(headers, rows) {
    return el("div", { class: "card table-card", style: "overflow-x:auto" }, [
      el("table", { class: "data-table" }, [
        el("thead", null, [el("tr", null, headers.map((h) => el("th", { class: h.numeric ? "ui-num" : "", text: h.label })))]),
        el("tbody", null, rows.length ? rows : [el("tr", null, [el("td", { colspan: headers.length, class: "ui-muted", text: "Nothing to show yet." })])])
      ])
    ]);
  }

  window.trayUI = {
    el, money, rupeesToPaise, canteenToday, addDays, formatDay, formatTime,
    describeError, fieldErrors, notice, errorNotice, header, demoOnly,
    csvCell, downloadCsv, table
  };
})();
