(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    qr: $("display-qr"),
    countdown: $("display-countdown"),
    message: $("display-message"),
    connectionIndicator: $("connection-indicator"),
    connectionText: $("connection-text"),
    revoke: $("revoke-codes")
  };

  let expiresAt = 0;
  let refreshTimer = null;
  let tickTimer = null;
  let stopped = false;

  function setConnection(online, text) {
    els.connectionIndicator.dataset.state = online ? "online" : "offline";
    els.connectionText.textContent = text;
  }

  function stopAll(message) {
    stopped = true;
    clearTimeout(refreshTimer);
    clearInterval(tickTimer);
    els.qr.innerHTML = "";
    els.countdown.textContent = "";
    els.message.textContent = message;
  }

  function tick() {
    const remaining = Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
    els.countdown.textContent = remaining > 0 ? `Code changes in ${remaining}s` : "Changing code…";
  }

  async function refreshCode() {
    if (stopped) return;
    clearTimeout(refreshTimer);
    try {
      const response = await trayApi.get("/presence/display-code");
      const data = response.data;
      // The SVG comes from our server and contains no user input.
      els.qr.innerHTML = data.qr_svg;
      expiresAt = Date.now() + data.ttl_seconds * 1000;
      els.message.textContent = "";
      setConnection(true, "Live");
      tick();
      refreshTimer = setTimeout(refreshCode, data.ttl_seconds * 1000);
    } catch (error) {
      if (error.status === 401) {
        stopAll("Sign in with a staff account to show the canteen code.");
        setConnection(false, "Signed out");
        return;
      }
      if (error.status === 403) {
        stopAll("This account can't show the canteen code. Use a kitchen or admin account.");
        setConnection(false, "Not authorized");
        return;
      }
      setConnection(false, error.status === undefined ? "Reconnecting…" : "Unavailable");
      els.message.textContent = error.status === undefined
        ? "Connection lost. Retrying…"
        : (error.message || "Could not load the code. Retrying…");
      refreshTimer = setTimeout(refreshCode, 3000);
    }
  }

  async function checkAccount() {
    try {
      const me = await trayApi.get("/auth/me");
      const role = String(me?.data?.role || "").toUpperCase();
      if (role === "KITCHEN" || role === "ADMIN") return true;
      stopAll("This screen needs a kitchen or admin account.");
      return false;
    } catch (error) {
      if (error.status === 401) {
        stopAll("Sign in with a staff account to show the canteen code.");
        els.message.innerHTML = "";
        const link = document.createElement("a");
        link.href = "./login.html";
        link.textContent = "Go to staff sign-in";
        els.message.appendChild(link);
        return false;
      }
      setConnection(false, "Can't reach TrayUP");
      return false;
    }
  }

  els.revoke.addEventListener("click", async () => {
    if (!window.confirm("Stop every live code now? Students will need the code that appears on this screen next.")) return;
    try {
      const response = await trayApi.post("/presence/revoke", {});
      trayNotify(`Revoked ${response.data.revoked} live code(s)`);
      await refreshCode();
    } catch (error) {
      trayNotify(error.message || "Could not revoke the codes");
    }
  });

  // Browsers may pause timers while the screen sleeps. Refresh immediately when it wakes up.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && !stopped && Date.now() >= expiresAt) refreshCode();
  });

  async function init() {
    tickTimer = setInterval(tick, 250);
    if (await checkAccount()) {
      refreshCode();
    }
  }

  init();
})();
