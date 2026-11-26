(function () {
  const demoMode = new URLSearchParams(window.location.search).get("demo") === "1";
  const statuses = ["received","preparing","ready","collected"];
  const demoQueue = {
    received: [
      {id:101,order_number:"TUP-4821",created_at:"10:24 AM",items:[{name:"Masala Dosa",quantity:2},{name:"Cold Coffee",quantity:1}]},
      {id:102,order_number:"TUP-4825",created_at:"10:31 AM",items:[{name:"Grilled Chicken Bowl",quantity:1}]}
    ],
    preparing:[{id:103,order_number:"TUP-4818",created_at:"10:11 AM",items:[{name:"Paneer Butter Masala",quantity:2}]}],
    ready:[{id:104,order_number:"TUP-4809",created_at:"9:58 AM",items:[{name:"Cheese Chilli Sandwich",quantity:2},{name:"Mango Shake",quantity:2}]}],
    collected:[{id:105,order_number:"TUP-4802",created_at:"9:40 AM",items:[{name:"Masala Dosa",quantity:1}] }]
  };
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  function updateTime() {
    document.getElementById("live-time").textContent = new Date().toLocaleString("en-IN", {
      weekday:"short",day:"numeric",month:"short",hour:"2-digit",minute:"2-digit"
    });
  }
  updateTime();
  const clock = setInterval(updateTime, 30000);
  window.addEventListener("pagehide", () => clearInterval(clock));

  function showError(detail) {
    document.getElementById("summary").textContent = detail;
    statuses.forEach(status => {
      const col = document.querySelector('[data-status="' + status + '"]');
      const heading = col.querySelector("h2");
      col.textContent = ""; col.appendChild(heading);
      const p = document.createElement("p");
      p.className = "empty-state"; p.textContent = detail; col.appendChild(p);
    });
  }
  function render(queue, readOnly) {
    const counts = statuses.map(s => Array.isArray(queue[s]) ? queue[s].length : 0);
    document.getElementById("summary").innerHTML =
      (readOnly ? '<div class="metric"><span>Mode</span><strong>Demo · read only</strong></div>' : "") +
      [["New",counts[0]],["Preparing",counts[1]],["Ready",counts[2]],["Collected",counts[3]]]
        .map(([label,value]) => '<div class="metric"><span>' + label + '</span><strong>' + value + '</strong></div>').join("");
    statuses.forEach(status => {
      const col = document.querySelector('[data-status="' + status + '"]');
      const heading = col.querySelector("h2").outerHTML;
      const orders = Array.isArray(queue[status]) ? queue[status] : [];
      const cards = orders.map(order => {
        const id = Number(order.id);
        const safeId = Number.isInteger(id) && id > 0 ? String(id) : "";
        const items = (order.items || []).map(item =>
          "<li><span>" + Math.max(1,Number(item.quantity)||1) + " × " +
          esc(item.item_name || item.name || item.menu_item_name || "Item") + "</span></li>"
        ).join("");
        const action = readOnly ? "" :
          (status==="received" ? '<button class="btn btn-primary" data-next="preparing">Start preparing</button>' : "") +
          (status==="preparing" ? '<button class="btn btn-primary" data-next="ready">Mark ready</button>' : "") +
          (status==="ready" ? '<button class="btn btn-secondary" data-next="collected">Confirm collection</button>' : "");
        return '<article class="order-ticket" data-order="' + safeId + '"><header><span>' +
          esc(order.order_number || "Order") + "</span><span>" + esc(order.created_at || "") +
          "</span></header><ul>" + items + "</ul>" + action + "</article>";
      }).join("");
      col.innerHTML = heading + (cards || '<div class="empty-state" style="background:transparent">No orders</div>');
    });
  }
  async function load() {
    if (demoMode) return render(demoQueue, true);
    try {
      const response = await trayApi.get("/kitchen/orders");
      render(response?.data?.queue || {}, false);
    } catch (error) {
      showError(error.status===401 ? "Please sign in with a kitchen account." :
        error.status===403 ? "This account does not have kitchen access." :
        "Unable to load live orders. Retry when the backend is available.");
    }
  }
  document.getElementById("kitchen-board").addEventListener("click", async event => {
    const button = event.target.closest("[data-next]");
    if (!button || demoMode) return;
    const ticket = button.closest("[data-order]");
    if (!ticket || !ticket.dataset.order) return;
    button.disabled = true;
    try {
      await trayApi.patch("/kitchen/orders/" + ticket.dataset.order + "/status", {status:button.dataset.next});
      trayNotify("Order status updated."); await load();
    } catch (error) {
      button.disabled = false; trayNotify(error.message || "Could not update order status.");
    }
  });
  document.getElementById("logout").addEventListener("click", async () => {
    try { await trayAuth.logout(); } catch (_) {}
    window.location.href = "./login.html";
  });
  load();
  if (!demoMode) {
    const poll = setInterval(load,15000);
    window.addEventListener("pagehide",()=>clearInterval(poll));
  }
})();
