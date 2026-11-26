// Shared shell and helpers for the administrator panel.
//
// Rules for everything in this file:
// - It never stores data in the browser. It has no storage of its own and sets no cookies.
// - Every value from the server is written with textContent or as an attribute, never as HTML.
// - It contains no sample data. Each page loads its figures from the API.
(function () {
  "use strict";

  const TIME_ZONE = "Asia/Kolkata";
  const SVG_NS = "http://www.w3.org/2000/svg";

  // ---------- DOM ----------

  // Builds an element. Text is always set with textContent. Event handlers are passed as on* props.
  function el(tag, props, children) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([key, value]) => {
      if (value === undefined || value === null || value === false) return;
      if (key === "text") node.textContent = String(value);
      else if (key === "class") node.className = String(value);
      else if (key === "dataset") Object.entries(value).forEach(([k, v]) => { node.dataset[k] = String(v); });
      else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
      else if (value === true) node.setAttribute(key, "");
      else node.setAttribute(key, String(value));
    });
    (children || []).forEach((child) => {
      if (child === undefined || child === null || child === false) return;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return node;
  }

  function icon(pathData) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", "icon");
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", pathData);
    svg.appendChild(path);
    return svg;
  }

  const ICONS = {
    dashboard: "M3 13h8V3H3zM13 21h8v-8h-8zM13 3v6h8V3zM3 21h8v-6H3z",
    orders: "M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 3h6v4H9z",
    menu: "M4 6h16M4 12h16M4 18h10",
    categories: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
    reports: "M3 3v18h18M7 14l4-4 3 3 5-6",
    refunds: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5",
    staff: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8",
    settings: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1",
    logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
    menuToggle: "M4 7h16M4 12h16M4 17h16",
    close: "M6 6l12 12M18 6L6 18",
    alert: "M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"
  };

  // ---------- Money, dates and numbers ----------

  const MONEY = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  // Money is stored as integer paise. It is converted to rupees only for display.
  function money(paise) {
    return "₹" + MONEY.format(Number(paise || 0) / 100);
  }

  // Turns text such as "75", "75.5" or "1,200" into paise. Returns null for anything else.
  function rupeesToPaise(text) {
    const cleaned = String(text ?? "").replace(/[₹,\s]/g, "");
    if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
    return Math.round(Number(cleaned) * 100);
  }

  function canteenToday() {
    return new Date().toLocaleDateString("en-CA", { timeZone: TIME_ZONE });
  }

  function addDays(day, delta) {
    const date = new Date(day + "T00:00:00Z");
    date.setUTCDate(date.getUTCDate() + delta);
    return date.toISOString().slice(0, 10);
  }

  // Inclusive number of days between two YYYY-MM-DD strings. Returns NaN for invalid input.
  function dayCount(from, to) {
    const a = Date.parse(from + "T00:00:00Z");
    const b = Date.parse(to + "T00:00:00Z");
    if (Number.isNaN(a) || Number.isNaN(b)) return NaN;
    return Math.round((b - a) / 86400000) + 1;
  }

  function formatDay(day) {
    const date = new Date(day + "T00:00:00Z");
    return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  }

  function formatDateTime(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return String(iso);
    return date.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: TIME_ZONE });
  }

  // ---------- API results and errors ----------

  // Some endpoints wrap their payload in { success, message, data }, others return it directly.
  function unwrap(response) {
    return response && response.data !== undefined ? response.data : response;
  }

  // Turns an error from the API client into a message a staff member can act on.
  function describeError(error) {
    if (!error || typeof error.status !== "number") {
      return { text: "Could not reach the server. Check the connection and try again. Nothing was changed.", signIn: false };
    }
    if (error.status === 401 || error.code === "MFA_REQUIRED" || error.code === "MFA_SESSION_EXPIRED") {
      return { text: "Your session has ended. Sign in again to continue.", signIn: true };
    }
    if (error.status === 403) return { text: "Administrator access is required for this page.", signIn: false };
    if (error.status === 429) return { text: "Too many requests. Wait a moment and try again.", signIn: false };
    if (error.status >= 500) return { text: "The server could not complete this. Nothing was changed. Try again shortly.", signIn: false };
    return { text: error.message || "Something went wrong. Nothing was changed.", signIn: false };
  }

  function fieldDetails(error) {
    const details = error && error.data && error.data.details;
    return details && typeof details === "object" ? details : {};
  }

  // ---------- Forms ----------

  let fieldCounter = 0;

  // A labelled form control with its own error message slot.
  function field(options) {
    const id = "fld-" + (options.name || "x") + "-" + (++fieldCounter);
    let input;
    if (options.options) {
      input = el("select", { id, name: options.name, required: options.required, disabled: options.disabled },
        options.options.map(([value, label]) => el("option", { value, text: label, selected: String(value) === String(options.value ?? "") })));
    } else if (options.rows) {
      input = el("textarea", { id, name: options.name, rows: options.rows, maxlength: options.maxLength, placeholder: options.placeholder, required: options.required }, [String(options.value ?? "")]);
    } else {
      input = el("input", {
        id, name: options.name, type: options.type || "text", value: options.value ?? "",
        required: options.required, maxlength: options.maxLength, min: options.min, max: options.max,
        step: options.step, placeholder: options.placeholder, autocomplete: options.autocomplete,
        inputmode: options.inputmode, disabled: options.disabled, pattern: options.pattern
      });
    }
    const error = el("div", { class: "field-error", role: "alert", hidden: true });
    const node = el("div", { class: "field" + (options.wide ? " field-wide" : "") }, [
      el("label", { for: id, text: options.label }),
      input,
      options.hint ? el("div", { class: "field-hint", text: options.hint }) : null,
      error
    ]);
    return { node, input, error, name: options.name };
  }

  function setFieldErrors(fields, details) {
    fields.forEach((f) => {
      const message = details && details[f.name];
      if (message) {
        f.error.textContent = String(message);
        f.error.hidden = false;
        f.input.setAttribute("aria-invalid", "true");
      } else {
        f.error.textContent = "";
        f.error.hidden = true;
        f.input.removeAttribute("aria-invalid");
      }
    });
  }

  // Reads every named control in a form into a plain object. Values are strings or booleans.
  function readForm(form) {
    const data = {};
    Array.from(form.elements).forEach((control) => {
      if (!control.name) return;
      data[control.name] = control.type === "checkbox" ? control.checked : control.value;
    });
    return data;
  }

  // ---------- Feedback ----------

  let toastRoot = null;
  function toast(text, tone) {
    if (!toastRoot) {
      toastRoot = el("div", { class: "toast-stack", role: "status", "aria-live": "polite" });
      document.body.appendChild(toastRoot);
    }
    const node = el("div", { class: "toast" + (tone ? " toast-" + tone : ""), text });
    toastRoot.appendChild(node);
    setTimeout(() => node.remove(), 4200);
  }

  function notice(text, tone) {
    return el("div", { class: "notice notice-" + (tone || "info"), role: tone === "danger" ? "alert" : "status" }, [
      icon(ICONS.alert),
      el("span", { text })
    ]);
  }

  function errorNotice(error) {
    const described = describeError(error);
    const children = [icon(ICONS.alert), el("span", { text: described.text })];
    if (described.signIn) {
      children.push(el("a", { href: "login.html", class: "notice-link", text: "Sign in" }));
    }
    return el("div", { class: "notice notice-danger", role: "alert" }, children);
  }

  function loading(text) {
    return el("div", { class: "loading", role: "status" }, [el("span", { class: "spinner", "aria-hidden": "true" }), el("span", { text: text || "Loading…" })]);
  }

  function empty(text) {
    return el("div", { class: "empty" }, [el("p", { text })]);
  }

  // ---------- Dialogs ----------

  // Opens a modal dialog. Returns { close }. Escape and the close button dismiss it.
  function modal(options) {
    const previous = document.activeElement;
    const titleId = "modal-title-" + (++fieldCounter);
    const close = () => {
      overlay.remove();
      document.removeEventListener("keydown", onKey);
      if (previous && previous.focus) previous.focus();
      if (options.onClose) options.onClose();
    };
    const onKey = (event) => { if (event.key === "Escape") close(); };
    const overlay = el("div", { class: "modal-overlay" }, [
      el("div", { class: "modal" + (options.wide ? " modal-wide" : ""), role: "dialog", "aria-modal": "true", "aria-labelledby": titleId }, [
        el("div", { class: "modal-head" }, [
          el("h2", { id: titleId, text: options.title }),
          el("button", { class: "icon-button", type: "button", "aria-label": "Close", onclick: close }, [icon(ICONS.close)])
        ]),
        el("div", { class: "modal-body" }, [options.body]),
        options.footer ? el("div", { class: "modal-foot" }, [options.footer]) : null
      ])
    ]);
    overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
    document.addEventListener("keydown", onKey);
    document.body.appendChild(overlay);
    const focusable = overlay.querySelector("input, select, textarea, button");
    if (focusable) focusable.focus();
    return { close, node: overlay };
  }

  // Resolves true when the admin confirms, false otherwise.
  function confirmAction(options) {
    return new Promise((resolve) => {
      let answered = false;
      const done = (value) => { if (!answered) { answered = true; dialog.close(); resolve(value); } };
      const dialog = modal({
        title: options.title,
        body: el("p", { class: "modal-text", text: options.message }),
        footer: el("div", { class: "button-row" }, [
          el("button", { class: "btn btn-ghost", type: "button", onclick: () => done(false), text: options.cancelLabel || "Cancel" }),
          el("button", { class: "btn " + (options.danger ? "btn-danger" : "btn-primary"), type: "button", onclick: () => done(true), text: options.confirmLabel || "Confirm" })
        ]),
        onClose: () => { if (!answered) { answered = true; resolve(false); } }
      });
    });
  }

  // ---------- Layout pieces ----------

  function pageHead(title, subtitle, actions) {
    return el("div", { class: "page-head" }, [
      el("div", null, [
        el("h1", { class: "page-title", text: title }),
        subtitle ? el("p", { class: "page-subtitle", text: subtitle }) : null
      ]),
      actions ? el("div", { class: "page-actions" }, actions) : null
    ]);
  }

  function card(options) {
    return el("section", { class: "card" + (options.class ? " " + options.class : "") }, [
      options.title || options.actions
        ? el("header", { class: "card-head" }, [
            el("div", null, [
              options.title ? el("h2", { class: "card-title", text: options.title }) : null,
              options.subtitle ? el("p", { class: "card-subtitle", text: options.subtitle }) : null
            ]),
            options.actions ? el("div", { class: "card-actions" }, options.actions) : null
          ])
        : null,
      el("div", { class: "card-body" }, Array.isArray(options.body) ? options.body : [options.body])
    ]);
  }

  function stat(label, value, hint, tone) {
    return el("div", { class: "stat" + (tone ? " stat-" + tone : "") }, [
      el("span", { class: "stat-label", text: label }),
      el("strong", { class: "stat-value", text: value }),
      hint ? el("span", { class: "stat-hint", text: hint }) : null
    ]);
  }

  const ORDER_STATUS = {
    pending_payment: ["Awaiting payment", "muted"],
    received: ["Received", "info"],
    preparing: ["Preparing", "warning"],
    ready: ["Ready", "success"],
    collected: ["Collected", "success"],
    cancelled: ["Cancelled", "danger"]
  };
  const PAYMENT_STATUS = {
    pending: ["Pending", "muted"],
    paid: ["Paid", "success"],
    failed: ["Failed", "danger"],
    refunded: ["Refunded", "info"],
    partially_refunded: ["Partly refunded", "warning"]
  };

  function badge(map, value) {
    const [label, tone] = map[value] || [value || "—", "muted"];
    return el("span", { class: "badge badge-" + tone, text: label });
  }

  function orderStatusBadge(value) { return badge(ORDER_STATUS, value); }
  function paymentStatusBadge(value) { return badge(PAYMENT_STATUS, value); }

  // headers: [{ label, numeric }]. rows: arrays of nodes or strings.
  function table(headers, rows, emptyText) {
    const body = rows.length
      ? rows.map((cells) => el("tr", null, cells.map((cell, index) =>
          el("td", { class: headers[index] && headers[index].numeric ? "num" : null }, [cell]))))
      : [el("tr", null, [el("td", { colspan: headers.length, class: "table-empty", text: emptyText || "Nothing to show yet." })])];
    return el("div", { class: "table-wrap" }, [
      el("table", { class: "data-table" }, [
        el("thead", null, [el("tr", null, headers.map((h) => el("th", { class: h.numeric ? "num" : null, scope: "col", text: h.label })))]),
        el("tbody", null, body)
      ])
    ]);
  }

  // Vertical bar chart drawn with DOM elements. items: array. value(item) must be a number.
  function barChart(items, options) {
    const max = Math.max(1, ...items.map((item) => Number(options.value(item)) || 0));
    return el("div", { class: "bar-chart", role: "img", "aria-label": options.label || "Chart" },
      items.map((item) => {
        const value = Number(options.value(item)) || 0;
        const height = Math.max(2, Math.round((value / max) * 100));
        return el("div", { class: "bar-col", title: options.tooltip ? options.tooltip(item) : String(value) }, [
          el("div", { class: "bar-track" }, [el("div", { class: "bar-fill", style: "height:" + height + "%" })]),
          el("span", { class: "bar-label", text: options.caption(item) })
        ]);
      }));
  }

  // Ranked horizontal bars. items: array; label/value/format are functions of an item.
  function rankedList(items, options) {
    if (!items.length) return empty(options.empty || "Nothing to show for this period.");
    const max = Math.max(1, ...items.map((item) => Number(options.value(item)) || 0));
    return el("div", { class: "ranked" }, items.map((item) => {
      const value = Number(options.value(item)) || 0;
      return el("div", { class: "ranked-row" }, [
        el("div", { class: "ranked-head" }, [
          el("strong", { text: options.label(item) }),
          el("span", { class: "cell-muted", text: options.format ? options.format(item) : String(value) })
        ]),
        el("div", { class: "ranked-track", role: "presentation" }, [
          el("div", { class: "ranked-fill", style: "width:" + Math.round((value / max) * 100) + "%" })
        ])
      ]);
    }));
  }

  // Key/value list. pairs: [[label, node-or-string], ...]
  function keyValues(pairs) {
    return el("dl", { class: "kv" }, pairs.flatMap(([label, value]) => [
      el("dt", { text: label }),
      el("dd", null, [typeof value === "string" ? document.createTextNode(value) : value])
    ]));
  }

  // ---------- CSV ----------

  // Protects against spreadsheet formula injection by prefixing cells that start with a formula character.
  function csvCell(value) {
    let text = value === null || value === undefined ? "" : String(value);
    if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return /[",\n\r]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  function csvText(rows) {
    return "\ufeff" + rows.map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
  }

  function downloadCsv(filename, rows) {
    const blob = new Blob([csvText(rows)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = el("a", { href: url, download: filename });
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // ---------- Shell ----------

  const NAV = [
    { key: "dashboard", label: "Overview", href: "dashboard.html" },
    { key: "orders", label: "Orders", href: "orders.html" },
    { key: "menu", label: "Menu", href: "menu.html" },
    { key: "categories", label: "Categories", href: "categories.html" },
    { key: "reports", label: "Reports", href: "reports.html" },
    { key: "refunds", label: "Refunds", href: "refunds.html" },
    { key: "staff", label: "Staff", href: "staff.html" },
    { key: "settings", label: "Settings", href: "settings.html" }
  ];

  function redirectToLogin() {
    window.location.replace("login.html");
  }

  async function signOut() {
    try {
      await trayAuth.logout();
    } catch (_) {
      toast("Could not sign out. Check the connection and try again.", "danger");
      return;
    }
    window.location.replace("login.html");
  }

  // Builds the sidebar and top bar around the page's #app element, checks the administrator's
  // session, and then calls run(context). The page's content goes into context.content.
  async function start(config) {
    const app = document.getElementById("app");
    if (!app) throw new Error("Page is missing its #app element.");
    document.title = config.title + " — trayUP Admin";

    const menuButton = el("button", { class: "icon-button menu-toggle", type: "button", "aria-label": "Open navigation", "aria-expanded": "false" }, [icon(ICONS.menuToggle)]);
    const sidebar = el("aside", { class: "sidebar", id: "sidebar" }, [
      el("a", { class: "brand", href: "dashboard.html" }, [
        el("span", { class: "brand-mark", "aria-hidden": "true", text: "T" }),
        el("span", { class: "brand-name", text: "trayUP" }),
        el("span", { class: "brand-tag", text: "Admin" })
      ]),
      el("nav", { class: "nav", "aria-label": "Administration" }, NAV.map((item) =>
        el("a", { href: item.href, class: "nav-link" + (item.key === config.page ? " is-active" : ""), "aria-current": item.key === config.page ? "page" : null }, [
          icon(ICONS[item.key] || ICONS.dashboard),
          el("span", { text: item.label })
        ])))
    ]);

    const userName = el("span", { class: "user-name", text: "Signing in…" });
    const userRole = el("span", { class: "user-role", text: "" });
    const logout = el("button", { class: "btn btn-ghost btn-small", type: "button", onclick: signOut }, [icon(ICONS.logout), el("span", { text: "Sign out" })]);
    const topbar = el("header", { class: "topbar" }, [
      menuButton,
      el("div", { class: "topbar-title", text: config.title }),
      el("div", { class: "topbar-user" }, [el("div", { class: "user-meta" }, [userName, userRole]), logout])
    ]);

    const content = el("div", { class: "page", id: "page" }, [loading("Loading…")]);
    app.replaceChildren(sidebar, el("div", { class: "main" }, [topbar, content]));

    menuButton.addEventListener("click", () => {
      const open = app.classList.toggle("nav-open");
      menuButton.setAttribute("aria-expanded", String(open));
    });

    let user;
    try {
      user = unwrap(await trayAuth.currentUser());
    } catch (error) {
      const described = describeError(error);
      if (described.signIn) return redirectToLogin();
      content.replaceChildren(errorNotice(error));
      return undefined;
    }

    userName.textContent = user.name || user.email || "Administrator";
    userRole.textContent = user.role === "ADMIN" ? "Administrator" : String(user.role || "");

    if (user.role !== "ADMIN") {
      content.replaceChildren(notice("This area is for administrators. Sign in with an administrator account.", "warning"));
      return undefined;
    }

    return config.run({ content, user, sidebar, app });
  }

  window.adminPanel = {
    el, icon, ICONS, money, rupeesToPaise, canteenToday, addDays, dayCount, formatDay, formatDateTime,
    unwrap, describeError, fieldDetails, field, setFieldErrors, readForm,
    toast, notice, errorNotice, loading, empty, modal, confirmAction,
    pageHead, card, stat, orderStatusBadge, paymentStatusBadge, table, barChart, rankedList, keyValues,
    csvCell, csvText, downloadCsv, start, redirectToLogin, NAV, TIME_ZONE
  };
})();
