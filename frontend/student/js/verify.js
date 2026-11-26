(function () {
  "use strict";

  document.getElementById("app-header").innerHTML = trayComponents.header("My Orders");

  const SESSION_KEY = "trayup-presence-session";
  const $ = (id) => document.getElementById(id);
  const els = {
    connectionIndicator: $("connection-indicator"),
    connectionText: $("connection-text"),
    loginRequired: $("login-required"),
    accountMessage: $("account-message"),
    mainPanel: $("main-panel"),
    scanState: document.getElementById("scan-state"),
    startScan: $("start-scan"),
    video: $("scanner-video"),
    verifyButton: $("verify-button"),
    verifyStatus: $("verify-status"),
    sessionPanel: $("session-panel"),
    sessionCountdown: $("session-countdown")
  };

  // Human-readable messages for the codes the backend returns.
  const CODE_MESSAGES = {
    QR_CODE_EXPIRED: "That code has expired. Scan the code currently on the canteen screen.",
    QR_CODE_REVOKED: "That code is no longer active. Scan the code currently on the canteen screen.",
    QR_CODE_ALREADY_USED: "You have already used this code. Scan the newer code on the screen.",
    INVALID_QR_CODE: "That isn't a valid canteen code. Scan the code on the screen.",
    OUTSIDE_CANTEEN_AREA: "You appear to be outside the canteen area. Go to the canteen and try again.",
    LOCATION_ACCURACY_TOO_LOW: "Your GPS signal is too weak. Move outdoors or near a window, then try again.",
    LOCATION_STALE: "That location reading was too old. Tap Verify my location again.",
    LOCATION_INVALID: "Your location could not be read. Try again.",
    PRESENCE_NOT_CONFIGURED: "Ordering is unavailable right now. Please ask the canteen staff."
  };

  let presenceToken = null;   // Held in memory only. It expires in seconds anyway.
  let scanStream = null;
  let scanFrame = null;
  let countdownTimer = null;
  let accountOk = false;
  let busy = false;

  function setStatus(message, tone) {
    els.verifyStatus.textContent = message;
    els.verifyStatus.dataset.tone = tone || "";
  }

  function setConnection(online, text) {
    els.connectionIndicator.dataset.state = online ? "online" : "offline";
    els.connectionText.textContent = text;
  }

  function formatTime(ms) {
    const total = Math.max(0, Math.ceil(ms / 1000));
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  // Read the code from the QR link: verify.html#presence=TOKEN. The fragment is never sent to the server.
  function readTokenFromLink() {
    const match = /(?:^|[#&])presence=([A-Za-z0-9_-]{32,128})/.exec(window.location.hash || "");
    if (match) {
      presenceToken = match[1];
      // Remove the code from the address bar so it isn't left in history or in a shared URL.
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
  }

  function readSession() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null");
      if (saved && typeof saved.token === "string" && Number.isFinite(saved.expiresAt) && saved.expiresAt > Date.now()) {
        return saved;
      }
    } catch (_) {}
    sessionStorage.removeItem(SESSION_KEY);
    return null;
  }

  function showSession() {
    clearInterval(countdownTimer);
    const saved = readSession();
    els.sessionPanel.hidden = !saved;
    if (!saved) return;

    const tick = () => {
      const remaining = saved.expiresAt - Date.now();
      if (remaining <= 0) {
        clearInterval(countdownTimer);
        sessionStorage.removeItem(SESSION_KEY);
        els.sessionPanel.hidden = true;
        setStatus("Your verification has expired. Scan the code and verify again.", "warn");
        return;
      }
      els.sessionCountdown.textContent = formatTime(remaining);
    };
    tick();
    countdownTimer = setInterval(tick, 250);
  }

  function updateScanState() {
    els.scanState.textContent = presenceToken
      ? "Code received. Tap Verify my location when you're ready."
      : "No code yet. Scan the code on the screen.";
    els.verifyButton.disabled = !presenceToken || busy || !accountOk || !navigator.onLine;
  }

  async function loadAccount() {
    try {
      const me = await trayApi.get("/auth/me");
      const role = String(me?.data?.role || "").toUpperCase();
      accountOk = role === "STUDENT";
      els.loginRequired.hidden = accountOk;
      els.mainPanel.hidden = !accountOk;
      if (!accountOk) {
        els.accountMessage.textContent = "This page is for student accounts. Staff accounts can't place orders.";
      }
    } catch (error) {
      if (error.status === 401) {
        accountOk = false;
        els.loginRequired.hidden = false;
        els.mainPanel.hidden = true;
        els.accountMessage.textContent = "Students need an account to order. Log in, then scan the canteen code again.";
      } else {
        setConnection(false, "Can't reach TrayUP. Check your connection.");
      }
    }
  }

  function updateConnection() {
    if (navigator.onLine) {
      setConnection(true, "Connected");
    } else {
      setConnection(false, "Offline. Reconnect to verify.");
    }
    updateScanState();
  }

  function stopScanner() {
    if (scanFrame) cancelAnimationFrame(scanFrame);
    scanFrame = null;
    if (scanStream) scanStream.getTracks().forEach((track) => track.stop());
    scanStream = null;
    els.video.hidden = true;
    els.video.srcObject = null;
  }

  async function startScanner() {
    if (scanStream) return;
    if (!("BarcodeDetector" in window) || !navigator.mediaDevices?.getUserMedia) {
      setStatus("This browser can't scan codes here. Open your phone's camera app and scan the code. The page will open with the code filled in.", "warn");
      return;
    }

    try {
      scanStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    } catch (_) {
      setStatus("Camera access was blocked. Allow camera access, or scan with your phone's camera app.", "warn");
      return;
    }

    els.video.srcObject = scanStream;
    els.video.hidden = false;
    await els.video.play().catch(() => {});

    const detector = new BarcodeDetector({ formats: ["qr_code"] });
    const scan = async () => {
      if (!scanStream) return;
      try {
        const codes = await detector.detect(els.video);
        for (const code of codes) {
          const match = /presence=([A-Za-z0-9_-]{32,128})/.exec(code.rawValue || "");
          if (match) {
            presenceToken = match[1];
            stopScanner();
            setStatus("", "");
            updateScanState();
            return;
          }
        }
      } catch (_) {}
      scanFrame = requestAnimationFrame(scan);
    };
    scan();
  }

  function getPosition() {
    return new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true,
        timeout: 15000,
        maximumAge: 0
      });
    });
  }

  function locationErrorMessage(error) {
    switch (error && error.code) {
      case 1:
        return "Location permission was denied. Allow location for this site in your browser settings, then try again. Location is needed to confirm you're at the canteen.";
      case 2:
        return "Your location isn't available right now. Turn on GPS and try again.";
      case 3:
        return "Finding your location took too long. Move outdoors or near a window, then try again.";
      default:
        return "Your location could not be read. Try again.";
    }
  }

  function verifyErrorMessage(error) {
    if (error.status === 401) return "Your session has ended. Log in again, then scan the code.";
    if (error.status === 403 && error.code === "FORBIDDEN") return "Only student accounts can verify presence.";
    if (error.status === 429) return "Too many attempts. Wait a minute and try again.";
    if (error.code && CODE_MESSAGES[error.code]) return CODE_MESSAGES[error.code];
    if (error.status === undefined) return "Can't reach TrayUP. Check your connection and try again.";
    return error.message || "Verification failed. Try again.";
  }

  async function verifyLocation() {
    if (busy) return;
    if (!presenceToken) {
      setStatus("Scan the canteen code first.", "warn");
      return;
    }
    if (!("geolocation" in navigator)) {
      setStatus("Your browser can't share location, so ordering isn't possible here. Try another browser.", "error");
      return;
    }

    busy = true;
    updateScanState();
    setStatus("Waiting for your permission to read your location…", "");

    let position;
    try {
      position = await getPosition();
    } catch (error) {
      busy = false;
      updateScanState();
      setStatus(locationErrorMessage(error), "error");
      return;
    }

    setStatus("Checking that you're at the canteen…", "");
    try {
      // Only these four values leave the device. They are never stored in the browser.
      const response = await trayApi.post("/presence/verify", {
        token: presenceToken,
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: position.coords.accuracy,
        timestamp: position.timestamp
      });
      const data = response.data;
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({
        token: data.session_token,
        expiresAt: Date.now() + data.expires_in_seconds * 1000
      }));
      presenceToken = null; // One code, one verification, on this device.
      setStatus("You're verified. Place your order before the timer runs out.", "ok");
      showSession();
    } catch (error) {
      if (error.code === "QR_CODE_EXPIRED" || error.code === "QR_CODE_REVOKED" || error.code === "QR_CODE_ALREADY_USED") {
        presenceToken = null;
      }
      setStatus(verifyErrorMessage(error), "error");
    } finally {
      busy = false;
      updateScanState();
    }
  }

  async function init() {
    readTokenFromLink();
    updateConnection();
    showSession();
    await loadAccount();
    updateScanState();

    window.addEventListener("online", updateConnection);
    window.addEventListener("offline", updateConnection);
    els.startScan.addEventListener("click", startScanner);
    els.verifyButton.addEventListener("click", verifyLocation);
    window.addEventListener("pagehide", stopScanner);

    if (presenceToken) setStatus("Code received from the link. Tap Verify my location.", "ok");
  }

  init();
})();
