// Refunds: payments that can still be refunded, the refund form, and recent refunds. The server sends
// every refund to the payment provider and reports back whether it was accepted.
(function () {
  "use strict";
  const P = window.adminPanel;
  const el = P.el;
  const REFUND_STATUS = {
    pending: ["Pending", "warning"],
    processed: ["Processed", "success"],
    failed: ["Failed", "danger"]
  };

  function refundStatus(value) {
    const [label, tone] = REFUND_STATUS[value] || [value || "Unknown", "muted"];
    return el("span", { class: "badge badge-" + tone, text: label });
  }

  function refundDialog(payment, onDone) {
    const amount = P.field({
      label: "Amount (₹)", name: "amount", inputmode: "decimal",
      value: (payment.refundable_paise / 100).toFixed(2),
      hint: "Up to " + P.money(payment.refundable_paise) + ". Enter less for a partial refund."
    });
    const reason = P.field({ label: "Reason", name: "reason", rows: 3, maxLength: 255, required: true, hint: "Recorded with the refund.", wide: true });
    const error = el("div", { class: "field-error", role: "alert", hidden: true });
    const submit = el("button", { class: "btn btn-danger", type: "submit", text: "Issue refund" });
    const form = el("form", { class: "form-grid", novalidate: true }, [amount.node, reason.node, error]);
    const dialog = P.modal({
      title: "Refund " + (payment.order_number || "payment"),
      body: el("div", { class: "stack" }, [
        P.notice("The refund is sent to the customer through the payment provider. It shows as pending until the provider confirms it.", "info"),
        form
      ]),
      footer: el("div", { class: "button-row" }, [el("button", { class: "btn btn-ghost", type: "button", text: "Cancel", onclick: () => dialog.close() }), submit])
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const paise = P.rupeesToPaise(amount.input.value);
      const text = reason.input.value.trim();
      if (paise === null || paise < 1 || paise > payment.refundable_paise) {
        error.textContent = "Enter an amount between ₹0.01 and " + P.money(payment.refundable_paise) + ".";
        error.hidden = false;
        return;
      }
      if (!text) { error.textContent = "Enter a reason for the refund."; error.hidden = false; return; }
      submit.disabled = true;
      try {
        await trayApi.post("/admin/payments/" + payment.payment_id + "/refund", { amount_paise: paise, reason: text });
        dialog.close();
        P.toast("Refund sent to the payment provider.", "success");
        onDone();
      } catch (err) {
        error.textContent = P.describeError(err).text;
        error.hidden = false;
        submit.disabled = false;
      }
    });
    amount.input.focus();
  }

  P.start({
    page: "refunds",
    title: "Refunds",
    run: ({ content }) => {
      const paymentsBox = el("div");
      const refundsBox = el("div");
      content.replaceChildren(
        P.pageHead("Refunds", "Payments that can still be refunded, and what has been sent back to customers."),
        P.card({ title: "Payments", subtitle: "Refund a payment in full or in part. Cancelled orders that were paid need a refund.", body: paymentsBox }),
        el("div", { style: "margin-top:18px" }, [P.card({ title: "Recent refunds", body: refundsBox })])
      );

      async function load() {
        paymentsBox.replaceChildren(P.loading("Loading payments…"));
        refundsBox.replaceChildren(P.loading("Loading refunds…"));
        const [paymentsRes, refundsRes] = await Promise.allSettled([
          trayApi.get("/admin/payments?limit=50"),
          trayApi.get("/admin/payments/refunds?limit=50")
        ]);

        if (paymentsRes.status === "fulfilled") {
          const payments = P.unwrap(paymentsRes.value).payments || [];
          paymentsBox.replaceChildren(P.table(
            [{ label: "Order" }, { label: "Paid", numeric: true }, { label: "Refunded", numeric: true }, { label: "Pending", numeric: true }, { label: "Refundable", numeric: true }, { label: "" }],
            payments.map((p) => [
              el("div", null, [
                el("div", { class: "cell-strong", text: p.order_number || "Order " + p.order_id }),
                el("div", { class: "cell-muted", text: P.formatDateTime(p.created_at) + " · " + (p.order_status || "") })
              ]),
              el("span", { class: "num", text: P.money(p.amount_paise) }),
              el("span", { class: "num", text: P.money(p.refunded_paise) }),
              el("span", { class: "num", text: P.money(p.pending_refund_paise) }),
              el("span", { class: "num cell-strong", text: P.money(p.refundable_paise) }),
              p.refundable_paise > 0
                ? el("button", { class: "btn btn-danger btn-small", type: "button", text: "Refund", "aria-label": "Refund " + (p.order_number || "payment"), onclick: () => refundDialog(p, load) })
                : el("span", { class: "cell-muted", text: "Nothing to refund" })
            ]),
            "No payments to show."
          ));
        } else {
          paymentsBox.replaceChildren(P.errorNotice(paymentsRes.reason));
        }

        if (refundsRes.status === "fulfilled") {
          const refunds = P.unwrap(refundsRes.value).refunds || [];
          refundsBox.replaceChildren(P.table(
            [{ label: "Issued" }, { label: "Order" }, { label: "Amount", numeric: true }, { label: "Status" }, { label: "Reason" }],
            refunds.map((r) => [
              el("span", { class: "cell-muted", text: P.formatDateTime(r.created_at) }),
              el("span", { text: r.order_number || "Order " + r.order_id }),
              el("span", { class: "num", text: P.money(r.amount_paise) }),
              refundStatus(r.status),
              el("span", { class: "cell-muted", text: r.reason || "" })
            ]),
            "No refunds have been issued yet."
          ));
        } else {
          refundsBox.replaceChildren(P.errorNotice(refundsRes.reason));
        }
      }

      load();
    }
  });
})();
