(function () {
  document.getElementById("app-header").innerHTML = trayComponents.header("My Orders");
  const target = document.getElementById("tracking");
  let orders = [];
  let menuById = new Map();

  const ORDER_STATUS_LABELS = {
    pending_payment: "Awaiting payment",
    received: "Received",
    preparing: "Preparing",
    ready: "Ready for collection",
    collected: "Collected",
    cancelled: "Cancelled"
  };
  const PAYMENT_STATUS_LABELS = {
    pending: "Pending",
    paid: "Paid",
    failed: "Failed",
    refunded: "Refunded",
    partially_refunded: "Partially refunded"
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;"
    })[character]);
  }

  function rupeesFromPaise(paise) {
    return `₹${(Number(paise || 0) / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  }

  function statusClass(status) {
    if (status === "cancelled") return "danger";
    if (status === "collected") return "";
    return "warning";
  }

  function renderMessage(title, message) {
    target.innerHTML = `<div class="empty-state"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p></div>`;
  }

  function renderOrders() {
    if (!orders.length) {
      renderMessage("No orders yet", "Orders you place will appear here.");
      return;
    }

    target.innerHTML = orders.map((order) => {
      const items = order.items || [];
      const orderStatus = order.order_status;
      const paymentStatus = order.payment_status;
      const statusLabel = ORDER_STATUS_LABELS[orderStatus] || orderStatus;
      const paymentLabel = PAYMENT_STATUS_LABELS[paymentStatus] || paymentStatus;
      const paymentComplete = paymentStatus === "paid";
      const orderComplete = orderStatus === "collected";
      const placed = new Date(order.created_at);
      const placedText = Number.isNaN(placed.getTime()) ? "" : placed.toLocaleString();

      const slides = items.map((line) => {
        const product = menuById.get(Number(line.menu_item_id));
        const image = product && product.image
          ? `<img src="${escapeHtml(product.image)}" alt="${escapeHtml(line.item_name)}" data-hide-on-error>`
          : "";
        return `
          <div class="order-food-slide">
            <div>
              <strong>${escapeHtml(line.item_name)}</strong>
              <p>Qty ${escapeHtml(line.quantity)} · ${rupeesFromPaise(line.unit_price_paise)} each</p>
              <p>${escapeHtml(product ? product.description : "")}</p>
              <strong>Line total: ${rupeesFromPaise(line.line_total_paise)}</strong>
            </div>
            ${image}
          </div>`;
      }).join("");

      return `
        <article class="card" style="margin-bottom:14px;padding:18px" data-order="${escapeHtml(order.id)}">
          <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start">
            <div>
              <strong class="receipt-order-number">Receipt ${escapeHtml(order.order_number)}</strong>
              <p style="color:var(--muted);font-size:13px;margin-top:5px">${items.length} item${items.length === 1 ? "" : "s"} · ${rupeesFromPaise(order.total_paise)}</p>
            </div>
            <span class="status ${statusClass(orderStatus)}">${escapeHtml(statusLabel)}</span>
          </div>
          <div class="order-progress order-progress-compact" aria-label="Order progress">
            <div class="progress-step complete"><span class="progress-circle"></span><span>Placed</span></div>
            <div class="progress-step ${paymentComplete ? "complete" : "active"}"><span class="progress-circle"></span><span>Payment</span></div>
            <div class="progress-step ${orderComplete ? "complete" : ""}"><span class="progress-circle"></span><span>Collected</span></div>
          </div>
          <div class="order-food-carousel">
            <div class="order-food-track" tabindex="0" aria-label="Ordered foods; swipe horizontally to view each item">${slides}</div>
            ${items.length > 1 ? `
              <div class="order-carousel-controls">
                <button type="button" data-carousel-prev aria-label="Previous food">‹</button>
                <span aria-live="polite"><span data-carousel-current>1</span> / ${items.length}</span>
                <button type="button" data-carousel-next aria-label="Next food">›</button>
              </div>` : ""}
          </div>
          <div class="order-details" hidden style="border-top:1px solid #eee;padding-top:12px;color:var(--muted);font-size:13px">
            ${placedText ? `Placed ${escapeHtml(placedText)} · ` : ""}Payment ${escapeHtml(paymentLabel)} · Total ${rupeesFromPaise(order.total_paise)}
          </div>
          <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px">
            <button class="btn btn-secondary" type="button" data-view="${escapeHtml(order.id)}">View Details</button>
            <button class="btn btn-primary" type="button" data-reorder="${escapeHtml(order.id)}" ${orderStatus === "cancelled" || !items.length || !menuById.size ? "disabled" : ""}>Reorder</button>
          </div>
        </article>`;
    }).join("");

    target.querySelectorAll(".order-food-track").forEach((track) => {
      track.addEventListener("scroll", () => {
        const current = track.closest(".order-food-carousel").querySelector("[data-carousel-current]");
        if (current) current.textContent = String(Math.round(track.scrollLeft / track.clientWidth) + 1);
      }, { passive: true });
    });

    if (pagination && pagination.has_next) {
      target.insertAdjacentHTML("beforeend", `
        <div class="load-more" style="text-align:center;margin-top:18px">
          <button class="btn btn-secondary" type="button" data-load-more ${loadingMore ? "disabled" : ""}>${loadingMore ? "Loading…" : "Load more orders"}</button>
          ${loadMoreError ? '<p class="status danger" style="margin-top:10px">We couldn’t load more orders. Try again.</p>' : ""}
        </div>`);
    }
  }

  // A failed load keeps the orders already on the page.
  async function loadMore() {
    if (loadingMore || !pagination || !pagination.has_next) return;
    loadingMore = true;
    loadMoreError = false;
    renderOrders();
    try {
      const response = await trayApi.get(`/orders?page=${pagination.page + 1}&per_page=${pagination.per_page}`);
      orders = orders.concat(response?.data?.orders || []);
      pagination = response?.data?.pagination || null;
    } catch (error) {
      if (error.status === 401) {
        window.location.href = "./login.html";
        return;
      }
      loadMoreError = true;
    } finally {
      loadingMore = false;
      renderOrders();
    }
  }

  function reorder(orderId) {
    const order = orders.find((entry) => String(entry.id) === String(orderId));
    if (!order) return;

    const cart = trayStorage.getCart();
    let added = 0;
    let skipped = 0;
    (order.items || []).forEach((line) => {
      const product = menuById.get(Number(line.menu_item_id));
      if (!product || !product.isAvailable) { skipped += 1; return; }
      const quantity = Math.max(1, Number(line.quantity) || 1);
      const existing = cart.find((item) => item.id === product.id);
      if (existing) existing.qty += quantity;
      else cart.push({ id: product.id, name: product.name, price: product.price, image: product.image, qty: quantity });
      added += 1;
    });

    if (!added) {
      trayNotify("None of these dishes are available right now.");
      return;
    }
    trayStorage.set("trayup-cart", cart);
    trayNotify(skipped ? `${skipped} dish${skipped === 1 ? "" : "es"} unavailable and not added.` : "Items added to your cart");
    window.location.href = "../student/cart.html";
  }

  target.addEventListener("click", (event) => {
    const previous = event.target.closest("[data-carousel-prev]");
    const next = event.target.closest("[data-carousel-next]");
    if (previous || next) {
      const track = (previous || next).closest(".order-food-carousel").querySelector(".order-food-track");
      track.scrollLeft += (next ? 1 : -1) * track.clientWidth;
      const current = track.closest(".order-food-carousel").querySelector("[data-carousel-current]");
      if (current) current.textContent = String(Math.round(track.scrollLeft / track.clientWidth) + 1);
      return;
    }

    const view = event.target.closest("[data-view]");
    if (view) {
      const details = view.closest("[data-order]").querySelector(".order-details");
      details.hidden = !details.hidden;
      view.textContent = details.hidden ? "View Details" : "Hide Details";
      return;
    }

    if (event.target.closest("[data-load-more]")) {
      loadMore();
      return;
    }

    const reorderButton = event.target.closest("[data-reorder]");
    if (reorderButton) reorder(reorderButton.dataset.reorder);
  });

  // Orders arrive in pages. The first page loads at once, and "Load more" adds the next one.
  let pagination = null;
  let loadMoreError = false;
  let loadingMore = false;
  const PAGE_SIZE = 10;

  async function load() {
    // Dish images and reorder need the menu. The orders still render without it.
    try {
      const dishes = await window.trayCatalog.list();
      menuById = new Map(dishes.map((dish) => [dish.id, dish]));
    } catch (_) {}

    try {
      const response = await trayApi.get(`/orders?page=1&per_page=${PAGE_SIZE}`);
      orders = response?.data?.orders || [];
      pagination = response?.data?.pagination || null;
      renderOrders();
    } catch (error) {
      if (error.status === 401) {
        window.location.href = "./login.html";
        return;
      }
      renderMessage("We couldn’t load your orders", "Check your connection and refresh the page.");
    }

    // Track My Order links here with ?order_id=, so bring that order into view.
    const focusId = Number(new URLSearchParams(window.location.search).get("order_id"));
    if (Number.isInteger(focusId) && focusId > 0) {
      const card = target.querySelector(`[data-order="${focusId}"]`);
      if (card && typeof card.scrollIntoView === "function") card.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  load();
})();
