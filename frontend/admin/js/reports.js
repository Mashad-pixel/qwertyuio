// Sales reports for a chosen range of canteen days. Every figure is loaded from /api/admin/reports/*.
(function () {
  "use strict";
  const P = window.adminPanel;
  const el = P.el;
  const MAX_DAYS = 366;

  function rangeFor(preset, today) {
    if (preset === "today") return { from: today, to: today };
    if (preset === "7") return { from: P.addDays(today, -6), to: today };
    return { from: P.addDays(today, -29), to: today };
  }

  function statusTiles(stats) {
    const names = { pending_payment: "Awaiting payment", received: "Received", preparing: "Preparing", ready: "Ready", collected: "Collected", cancelled: "Cancelled" };
    const byStatus = stats.by_order_status || {};
    return el("div", null, Object.entries(names).map(([key, label]) =>
      el("div", { class: "status-tile" }, [
        el("span", { text: label }),
        el("strong", { text: String(byStatus[key] || 0) })
      ])));
  }

  function csvRows(sales, items, categories, hours) {
    const rows = [["Section", "Date or name", "Orders or quantity", "Revenue (₹)", "Refunded (₹)"]];
    sales.days.forEach((d) => rows.push(["Day", d.date, d.orders, (d.revenue_paise / 100).toFixed(2), (d.refunded_paise / 100).toFixed(2)]));
    items.forEach((i) => rows.push(["Item", i.item_name, i.quantity, (i.revenue_paise / 100).toFixed(2), ""]));
    categories.forEach((c) => rows.push(["Category", c.category, c.quantity, (c.revenue_paise / 100).toFixed(2), ""]));
    hours.filter((h) => h.orders > 0).forEach((h) => rows.push(["Hour", String(h.hour).padStart(2, "0") + ":00", h.orders, "", ""]));
    return rows;
  }

  P.start({
    page: "reports",
    title: "Reports",
    run: ({ content }) => {
      const today = P.canteenToday();
      const state = { preset: "30", from: P.addDays(today, -29), to: today, data: null };

      const presetButtons = [["today", "Today"], ["7", "7 days"], ["30", "30 days"], ["custom", "Custom"]].map(([key, label]) =>
        el("button", { type: "button", "aria-pressed": String(state.preset === key), dataset: { preset: key }, text: label, onclick: () => choosePreset(key) }));
      const segmented = el("div", { class: "segmented", role: "group", "aria-label": "Date range" }, presetButtons);
      const fromField = P.field({ label: "From", name: "from", type: "date", value: state.from, max: today });
      const toField = P.field({ label: "To", name: "to", type: "date", value: state.to, max: today });
      const applyButton = el("button", { class: "btn btn-primary", type: "button", text: "Apply", onclick: () => applyCustom() });
      const customBar = el("div", { class: "toolbar", hidden: true }, [fromField.node, toField.node, applyButton]);
      const exportButton = el("button", { class: "btn btn-ghost", type: "button", text: "Export CSV", disabled: true, onclick: () => exportCsv() });
      const body = el("div", { class: "stack" });

      content.replaceChildren(
        P.pageHead("Reports", "Revenue, popular items and busy hours, in canteen time. Refunds reduce revenue on the day they were issued.", [exportButton]),
        el("div", { class: "toolbar" }, [segmented]),
        customBar,
        body
      );

      function choosePreset(key) {
        state.preset = key;
        presetButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.preset === key)));
        customBar.hidden = key !== "custom";
        if (key !== "custom") {
          const range = rangeFor(key, today);
          state.from = range.from;
          state.to = range.to;
          load();
        }
      }

      function applyCustom() {
        const from = fromField.input.value;
        const to = toField.input.value;
        const days = P.dayCount(from, to);
        const error = !from || !to ? "Choose both dates."
          : Number.isNaN(days) ? "Enter valid dates."
          : days < 1 ? "The end date must be on or after the start date."
          : days > MAX_DAYS ? "Choose a range of " + MAX_DAYS + " days or fewer."
          : to > today ? "The end date cannot be in the future."
          : "";
        if (error) { P.toast(error, "danger"); return; }
        state.from = from;
        state.to = to;
        load();
      }

      function exportCsv() {
        if (!state.data) return;
        const d = state.data;
        P.downloadCsv("trayup-report-" + state.from + "-to-" + state.to + ".csv",
          csvRows(d.sales, d.items, d.categories, d.hours));
      }

      function render(d) {
        const o = d.overview;
        const salesDays = d.sales.days || [];
        body.replaceChildren(
          el("div", { class: "grid grid-stats" }, [
            P.stat("Orders", String(o.total_orders), o.cancelled_orders + " cancelled"),
            P.stat("Paid orders", String(o.paid_orders)),
            P.stat("Gross revenue", P.money(o.gross_revenue_paise)),
            P.stat("Refunded", P.money(o.refunded_paise)),
            P.stat("Net revenue", P.money(o.net_revenue_paise), "After refunds", "accent"),
            P.stat("Average order", P.money(o.average_order_value_paise), "Paid orders")
          ]),
          el("div", { class: "grid grid-2", style: "margin-top:18px" }, [
            P.card({
              title: "Revenue by day",
              body: salesDays.length
                ? el("div", { class: "table-wrap" }, [el("table", { class: "data-table" }, [
                    el("thead", null, [el("tr", null, [el("th", { text: "Day" }), el("th", { class: "num", text: "Orders" }), el("th", { class: "num", text: "Revenue" }), el("th", { class: "num", text: "Refunded" })])]),
                    el("tbody", null, salesDays.map((x) => el("tr", null, [
                      el("td", { text: P.formatDay(x.date) }),
                      el("td", { class: "num", text: String(x.orders) }),
                      el("td", { class: "num", text: P.money(x.revenue_paise) }),
                      el("td", { class: "num", text: P.money(x.refunded_paise) })
                    ])))
                  ])])
                : P.empty("No sales in this period.")
            }),
            P.card({ title: "Order statuses", body: statusTiles(d.orderStats) })
          ]),
          el("div", { class: "grid grid-2", style: "margin-top:18px" }, [
            P.card({
              title: "Popular items",
              body: P.rankedList(d.items.items || [], {
                label: (i) => i.item_name,
                value: (i) => i.quantity,
                format: (i) => i.quantity + " sold · " + P.money(i.revenue_paise)
              })
            }),
            P.card({
              title: "Categories",
              body: P.rankedList(d.categories.categories || [], {
                label: (c) => c.category,
                value: (c) => c.revenue_paise,
                format: (c) => c.quantity + " sold · " + P.money(c.revenue_paise)
              })
            })
          ]),
          P.card({
            title: "Busiest hours",
            subtitle: "Orders placed in each hour of the canteen day",
            body: d.hours.hours.some((h) => h.orders > 0)
              ? P.barChart(d.hours.hours, {
                  label: "Orders by hour",
                  value: (h) => h.orders,
                  caption: (h) => (h.hour % 3 === 0 ? String(h.hour).padStart(2, "0") : ""),
                  tooltip: (h) => String(h.hour).padStart(2, "0") + ":00 — " + h.orders + " order(s)"
                })
              : P.empty("No orders in this period.")
          })
        );
      }

      async function load() {
        body.replaceChildren(P.loading("Loading report…"));
        exportButton.disabled = true;
        const query = "from=" + state.from + "&to=" + state.to;
        try {
          const [overview, sales, items, categories, hours, orderStats] = await Promise.all([
            trayApi.get("/admin/reports/overview?" + query),
            trayApi.get("/admin/reports/sales?" + query),
            trayApi.get("/admin/reports/popular-items?" + query + "&limit=10"),
            trayApi.get("/admin/reports/categories?" + query),
            trayApi.get("/admin/reports/peak-hours?" + query),
            trayApi.get("/admin/reports/orders?" + query)
          ]);
          state.data = {
            overview: P.unwrap(overview),
            sales: P.unwrap(sales),
            items: P.unwrap(items),
            categories: P.unwrap(categories),
            hours: P.unwrap(hours),
            orderStats: P.unwrap(orderStats)
          };
          render(state.data);
          exportButton.disabled = false;
        } catch (error) {
          body.replaceChildren(P.errorNotice(error));
        }
      }

      load();
    }
  });
})();
