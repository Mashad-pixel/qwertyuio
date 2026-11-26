// Administrator overview. Every figure comes from the reporting and order APIs for canteen-local days.
(function () {
  "use strict";
  const P = window.adminPanel;
  const el = P.el;

  function summaryStats(summary, accentRevenue) {
    return [
      P.stat("Orders", String(summary.total_orders), summary.cancelled_orders + " cancelled"),
      P.stat("Paid", String(summary.paid_orders)),
      P.stat("Gross revenue", P.money(summary.gross_revenue_paise), "Before refunds"),
      P.stat("Net revenue", P.money(summary.net_revenue_paise), "After refunds", accentRevenue ? "accent" : null),
      P.stat("Average order", P.money(summary.average_order_value_paise), "Paid orders"),
      P.stat("Collected", summary.completion_rate_percent + "%", summary.average_preparation_minutes != null ? "Avg prep " + summary.average_preparation_minutes + " min" : "Share of paid orders")
    ];
  }

  function recentTable(orders) {
    return P.table(
      [{ label: "Order" }, { label: "Customer" }, { label: "Total", numeric: true }, { label: "Status" }, { label: "Payment" }, { label: "Placed" }],
      orders.map((order) => [
        el("span", { class: "cell-strong", text: order.order_number }),
        order.student ? order.student.name : (order.customer_name || "Guest"),
        el("span", { text: P.money(order.total_paise) }),
        P.orderStatusBadge(order.order_status),
        P.paymentStatusBadge(order.payment_status),
        el("span", { class: "cell-muted", text: P.formatDateTime(order.created_at) })
      ]),
      "No orders yet."
    );
  }

  P.start({
    page: "dashboard",
    title: "Overview",
    run: async ({ content }) => {
      const today = P.canteenToday();
      const monthStart = P.addDays(today, -29);
      const range = "from=" + monthStart + "&to=" + today;
      const dayRange = "from=" + today + "&to=" + today;

      content.replaceChildren(
        P.pageHead("Overview", "Today and the last 30 canteen days, from live reports.", [
          el("a", { class: "btn btn-ghost", href: "orders.html", text: "All orders" }),
          el("a", { class: "btn btn-primary", href: "reports.html", text: "Detailed reports" })
        ]),
        P.loading("Loading figures…")
      );

      const results = await Promise.allSettled([
        trayApi.get("/admin/reports/overview?" + dayRange),
        trayApi.get("/admin/reports/overview?" + range),
        trayApi.get("/admin/reports/sales?" + range),
        trayApi.get("/admin/reports/popular-items?" + range + "&limit=6"),
        trayApi.get("/admin/orders?per_page=8"),
        trayApi.get("/canteen/status")
      ]);
      const [todayRes, monthRes, salesRes, popularRes, ordersRes, statusRes] = results.map((r) => (r.status === "fulfilled" ? r.value : null));
      const errorOf = (r) => (r.status === "rejected" ? r.reason : null);

      const status = statusRes ? P.unwrap(statusRes) : null;
      const chip = status
        ? el("span", { class: "badge badge-" + (status.is_accepting_orders ? "success" : "danger"), text: status.is_accepting_orders ? "Accepting orders" : "Orders paused" })
        : null;

      const sections = [];

      sections.push(P.card({
        title: "Today (" + P.formatDay(today) + ")",
        body: todayRes
          ? el("div", { class: "grid grid-stats" }, summaryStats(P.unwrap(todayRes), false))
          : P.errorNotice(errorOf(results[0]))
      }));

      sections.push(P.card({
        title: "Last 30 days",
        subtitle: P.formatDay(monthStart) + " to " + P.formatDay(today),
        body: monthRes
          ? el("div", { class: "grid grid-stats" }, summaryStats(P.unwrap(monthRes), true))
          : P.errorNotice(errorOf(results[1]))
      }));

      const salesDays = salesRes ? (P.unwrap(salesRes).days || []) : null;
      const salesCard = P.card({
        title: "Revenue by day",
        subtitle: "Gross paid revenue per canteen day",
        body: salesDays
          ? (salesDays.length
              ? P.barChart(salesDays, {
                  label: "Revenue by day",
                  value: (d) => d.revenue_paise,
                  caption: (d) => d.date.slice(8),
                  tooltip: (d) => P.formatDay(d.date) + ": " + P.money(d.revenue_paise) + " from " + d.orders + " order(s)"
                })
              : P.empty("No sales in this period."))
          : P.errorNotice(errorOf(results[2]))
      });

      const popular = popularRes ? (P.unwrap(popularRes).items || []) : null;
      const popularCard = P.card({
        title: "Top items",
        subtitle: "Most units sold in the last 30 days",
        body: popular
          ? P.rankedList(popular, {
              label: (i) => i.item_name,
              value: (i) => i.quantity,
              format: (i) => i.quantity + " sold · " + P.money(i.revenue_paise),
              empty: "No items sold in this period."
            })
          : P.errorNotice(errorOf(results[3]))
      });
      sections.push(el("div", { class: "grid grid-2" }, [salesCard, popularCard]));

      const orders = ordersRes ? (P.unwrap(ordersRes).orders || []) : null;
      sections.push(P.card({
        title: "Recent orders",
        actions: [el("a", { class: "btn btn-ghost btn-small", href: "orders.html", text: "View all" })],
        body: orders ? recentTable(orders) : P.errorNotice(errorOf(results[4]))
      }));

      content.replaceChildren(
        P.pageHead("Overview", "Today and the last 30 canteen days, from live reports.", [
          chip,
          el("a", { class: "btn btn-ghost", href: "orders.html", text: "All orders" }),
          el("a", { class: "btn btn-primary", href: "reports.html", text: "Detailed reports" })
        ]),
        el("div", { class: "stack" }, sections)
      );
    }
  });
})();
