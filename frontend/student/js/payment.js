(function () {
  // The server creates the Razorpay order, sets the amount, and verifies the signature.
  // The browser only opens Checkout and forwards the result. A Checkout success callback
  // alone never marks an order paid: the order is paid only after /payments/verify succeeds.

  function paymentError(message, code) {
    const error = new Error(message);
    error.code = code;
    return error;
  }

  window.trayPayment = {
    // Opens Razorpay Checkout for an order the server already created.
    // Resolves with the server's verification response once the payment is verified.
    // Rejects with code PAYMENT_CANCELLED when the student closes Checkout.
    pay: async function (orderId, student, callbacks) {
      const created = await trayApi.post("/payments/create-order", { order_id: orderId });
      const details = created?.data || {};

      if (!details.key_id || !details.razorpay_order_id) {
        throw paymentError("Online payment is not set up on this server yet.", "PAYMENTS_NOT_CONFIGURED");
      }
      if (typeof window.Razorpay !== "function") {
        throw paymentError("The payment window could not load. Check your connection and try again.", "CHECKOUT_NOT_LOADED");
      }

      return new Promise((resolve, reject) => {
        let settled = false;
        let verifying = false;
        const settle = (fn, value) => {
          if (settled) return;
          settled = true;
          fn(value);
        };

        const checkout = new window.Razorpay({
          key: details.key_id,
          amount: details.amount_paise,
          currency: details.currency || "INR",
          order_id: details.razorpay_order_id,
          name: window.TRAYUP_CONFIG?.appName || "TrayUP",
          description: details.order_number ? `Order ${details.order_number}` : "Canteen order",
          prefill: {
            name: student?.name || "",
            contact: student?.phone || ""
          },
          handler: async (response) => {
            verifying = true;
            try {
              const verified = await trayApi.post("/payments/verify", {
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature
              });
              settle(resolve, verified);
            } catch (error) {
              // A 4xx is a definite answer (bad signature, refund required, ...). A 5xx or a network
              // failure (no status) means the payment state is unknown, so the student must not pay again.
              const definite = error.status && error.status < 500;
              settle(reject, definite
                ? error
                : paymentError("We could not confirm your payment yet. Check Track orders before paying again.", "VERIFY_FAILED"));
            }
          },
          modal: {
            ondismiss: () => {
              // Ignore a dismiss that happens while the payment is being verified.
              if (!verifying) settle(reject, paymentError("Payment was cancelled.", "PAYMENT_CANCELLED"));
            }
          }
        });

        checkout.on("payment.failed", (event) => {
          // Razorpay keeps the Checkout window open so the student can retry. Only report it.
          callbacks?.onFailed?.(event?.error?.description || "Payment failed. You can try again.");
        });
        checkout.open();
      });
    }
  };
})();
