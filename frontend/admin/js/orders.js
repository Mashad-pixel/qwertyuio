// Orders: list with filters and pages, a detail view with items and status history, and cancellation.
(function () {
  "use strict";
  const P = window.adminPanel;
  const el = P.el;
  const PER_PAGE = 20;
  const ORDER_STATUS_OPTIONS = [
    ["", "All statuses"], ["pending_payment", "Awaiting payment"], ["received", "Received"],
    ["preparing", "Preparing"], ["ready", "Ready"], ["collected", "Collected"], ["cancelled", "Cancelled"]
  ];
  const PAYMENT_OPTIONS = [
    ["", "All payments"], ["pending", "Pending"], ["paid", "Paid"], ["failed", "Failed"],
    ["refunded", "Refunded"], ["partially_refunded", "Partly refunded"]
  ];
  const CANCELLABLE = new Set(["pending_payment", "received", "preparing", "ready"]);

  const state = { page: 1, orderStatus: "", paymentStatus: "" };

  function queryString() {
    const params = new URLSearchParams({ page: String(state.page), per_page: String(PER_PAGE) });
    if (state.orderStatus) params.set("order_status", state.orderStatus);
    if (state.paymentStatus) params.set("payment_status", state.paymentStatus);
    return params.toString();
  }

  function customerOf(order) {
    if (order.student) return order.student.name || order.student.email || "Student";
    return order.customer_name || "Guest";
  }

  function openDetail(orderId, onChanged) {
    const body = el("div", { class: "stack" }, [P.loading("Loading order…")]);
    const dialog = P.modal({ title: "Order", body, wide: true });

    trayApi.get("/admin/orders/" + orderId).then((response) => {
      const order = P.unwrap(response);
      body.replaceChildren(renderDetail(order, dialog, onChanged));
    }).catch((error) => {
      body.replaceChildren(P.errorNotice(error));
    });
  }

  function renderDetail(order, dialog, onChanged) {
    const items = order.items || [];
    const cancellable = CANCELLABLE.has(order.order_status);
    const needsRefund = order.order_status === "cancelled" && order.payment_status === "paid";

    const lines = el("div", { class: "line-items" }, items.map((item) =>
      el("div", { class: "line-item" }, [
        el("div", null, [
          el("strong", { text: item.quantity + " × " + item.item_name }),
          el("span", { class: "cell-muted", text: P.money(item.unit_price_paise) + " each" })
        ]),
        el("span", { text: P.money(item.line_total_paise) })
      ])
    ));

    const timeline = (order.status_history || []).length
      ? el("ol", { class: "timeline" }, order.status_history.map((entry) =>
          el("li", null, [
            el("strong", { text: (entry.previous_status || "new") + " → " + entry.new_status }),
            el("span", { class: "cell-muted", text: P.formatDateTime(entry.changed_at) + (entry.notes ? " · " + entry.notes : "") })
          ])))
      : P.empty("No status changes recorded.");

    const actions = [];
    if (cancellable) {
      actions.push(el("button", { class: "btn btn-danger", type: "button", text: "Cancel order", onclick: () => cancelDialog(order, dialog, onChanged) }));
    }

    return el("div", { class: "stack" }, [
      needsRefund ? P.notice("This order was cancelled after payment. Issue the refund from the Refunds page.", "warning") : null,
      el("div", { class: "grid grid-2" }, [
        P.card({
          title: order.order_number,
          subtitle: "Placed " + P.formatDateTime(order.created_at),
          body: P.keyValues([
            ["Status", P.orderStatusBadge(order.order_status)],
            ["Payment", P.paymentStatusBadge(order.payment_status)],
            ["Customer", customerOf(order)],
            ["Phone", order.customer_phone || (order.student ? order.student.email : "—")],
            ["Instructions", order.instructions || "None"]
          ])
        }),
        P.card({
          title: "Totals",
          body: [
            P.keyValues([
              ["Subtotal", P.money(order.subtotal_paise)],
              ["Discount", P.money(order.discount_paise)],
              ["Tax", P.money(order.tax_paise)]
            ]),
            el("div", { class: "total-row" }, [el("span", { text: "Total" }), el("span", { text: P.money(order.total_paise) })])
          ]
        })
      ]),
      P.card({ title: "Items", body: lines }),
      P.card({ title: "Status history", body: timeline }),
      actions.length ? el("div", { class: "button-row" }, actions) : null
    ]);
  }

  function cancelDialog(order, detailDialog, onChanged) {
    const reason = P.field({ label: "Reason", name: "reason", rows: 3, maxLength: 255, required: true, value: "", hint: "Shown in the order history. Up to 255 characters.", wide: true });
    const error = el("div", { class: "field-error", role: "alert", hidden: true });
    const submit = el("button", { class: "btn btn-danger", type: "submit", text: "Cancel order" });
    const form = el("form", { class: "stack", novalidate: true }, [reason.node, error]);
    const footer = el("div", { class: "button-row" }, [
      el("button", { class: "btn btn-ghost", type: "button", text: "Keep order", onclick: () => dialog.close() }),
      submit
    ]);
    const dialog = P.modal({ title: "Cancel " + order.order_number + "?", body: form, footer });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = reason.input.value.trim();
      if (!text) { error.textContent = "Enter a reason for the cancellation."; error.hidden = false; return; }
      submit.disabled = true;
      try {
        const response = await trayApi.post("/admin/orders/" + order.id + "/cancel", { reason: text });
        const result = P.unwrap(response);
        dialog.close();
        detailDialog.close();
        P.toast(result.refund_required
          ? "Order cancelled. Its payment must be refunded on the Refunds page."
          : "Order cancelled.", "success");
        onChanged();
      } catch (err) {
        error.textContent = P.describeError(err).text;
        error.hidden = false;
        submit.disabled = false;
      }
    });
    reason.input.focus();
  }

  P.start({
    page: "orders",
    title: "Orders",
    run: ({ content }) => {
      const orderStatus = P.field({ label: "Order status", name: "order_status", options: ORDER_STATUS_OPTIONS, value: "" });
      const paymentStatus = P.field({ label: "Payment", name: "payment_status", options: PAYMENT_OPTIONS, value: "" });
      orderStatus.input.addEventListener("change", () => { state.orderStatus = orderStatus.input.value; state.page = 1; load(); });
      paymentStatus.input.addEventListener("change", () => { state.paymentStatus = paymentStatus.input.value; state.page = 1; load(); });

      const results = el("div");
      const pager = el("div", { class: "pager" });
      const refresh = el("button", { class: "btn btn-ghost", type: "button", text: "Refresh", onclick: () => load() });

      content.replaceChildren(
        P.pageHead("Orders", "Every order, newest first. Open an order to see its items, history and actions.", [refresh]),
        el("div", { class: "toolbar" }, [orderStatus.node, paymentStatus.node]),
        el("div", { class: "card" }, [el("div", { class: "card-body" }, [results, pager])])
      );

      async function load() {
        results.replaceChildren(P.loading("Loading orders…"));
        pager.replaceChildren();
        try {
          const data = P.unwrap(await trayApi.get("/admin/orders?" + queryString()));
          const orders = data.orders || [];
          const info = data.pagination || { page: 1, pages: 1, total: orders.length };
          results.replaceChildren(P.table(
            [{ label: "Order" }, { label: "Customer" }, { label: "Total", numeric: true }, { label: "Status" }, { label: "Payment" }, { label: "Placed" }, { label: "" }],
            orders.map((order) => [
              el("span", { class: "cell-strong", text: order.order_number }),
              customerOf(order),
              el("span", { text: P.money(order.total_paise) }),
              P.orderStatusBadge(order.order_status),
              P.paymentStatusBadge(order.payment_status),
              el("span", { class: "cell-muted", text: P.formatDateTime(order.created_at) }),
              el("button", { class: "btn btn-ghost btn-small", type: "button", text: "Open", "aria-label": "Open order " + order.order_number, onclick: () => openDetail(order.id, load) })
            ]),
            "No orders match these filters."
          ));
          pager.replaceChildren(
            el("span", { text: info.total + " order(s) · page " + info.page + " of " + Math.max(info.pages, 1) }),
            el("div", { class: "button-row" }, [
              el("button", { class: "btn btn-ghost btn-small", type: "button", disabled: !info.has_prev, text: "Previous", onclick: () => { state.page -= 1; load(); } }),
              el("button", { class: "btn btn-ghost btn-small", type: "button", disabled: !info.has_next, text: "Next", onclick: () => { state.page += 1; load(); } })
            ])
          );
        } catch (error) {
          results.replaceChildren(P.errorNotice(error));
        }
      }

      load();
    }
  });
})();
