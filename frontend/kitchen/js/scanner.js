(function () {
  const form = document.getElementById("scan-form");
  const tokenInput = document.getElementById("token");
  const result = document.getElementById("scan-result");
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  })[c]);
  let stream = null;
  let scanning = false;

  function message(title, detail) {
    result.innerHTML = '<div class="empty-state"><strong>' + escapeHtml(title) +
      "</strong><p>" + escapeHtml(detail) + "</p></div>";
  }
  function stopCamera() {
    scanning = false;
    if (stream) { stream.getTracks().forEach((track) => track.stop()); stream = null; }
    const video = document.getElementById("camera");
    if (video) video.srcObject = null;
  }
  async function verify(token) {
    if (!token) return message("Collection not verified", "Enter or scan a collection code.");
    try {
      const response = await trayApi.post("/kitchen/collection/verify", {token});
      const orderNumber = escapeHtml(response?.data?.order_number || "Collection ready");
      result.innerHTML = '<div class="card" style="padding:16px"><span class="status">Valid code</span>' +
        '<p style="margin:10px 0 14px">' + orderNumber + '</p>' +
        '<button class="btn btn-primary" id="confirm-handover" type="button">Confirm handover</button></div>';
      document.getElementById("confirm-handover").addEventListener("click", () => confirmHandover(token));
      stopCamera();
    } catch (error) {
      message("Collection not verified", error.message || "Invalid or expired collection code.");
    }
  }
  async function confirmHandover(token) {
    const button = document.getElementById("confirm-handover");
    if (button) button.disabled = true;
    try {
      await trayApi.post("/kitchen/collection/confirm", {token});
      trayNotify("Order collected successfully.");
      message("Collection complete", "Handover was confirmed by the server.");
    } catch (error) {
      if (button) button.disabled = false;
      trayNotify(error.message || "Unable to confirm collection.");
    }
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    verify(tokenInput.value.trim());
  });
  async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) return;
    try {
      stream = await navigator.mediaDevices.getUserMedia({video:{facingMode:"environment"}});
      const video = document.getElementById("camera");
      video.srcObject = stream;
      video.hidden = false;
      await video.play();
      document.getElementById("scanner-placeholder").hidden = true;
      if (!("BarcodeDetector" in window)) return;
      const detector = new BarcodeDetector({formats:["qr_code"]});
      scanning = true;
      const scan = async () => {
        if (!scanning) return;
        try {
          const codes = await detector.detect(video);
          if (codes.length) {
            tokenInput.value = codes[0].rawValue;
            await verify(codes[0].rawValue);
            return;
          }
        } catch (_) {}
        if (scanning) requestAnimationFrame(scan);
      };
      scan();
    } catch (_) {
      document.getElementById("scanner-placeholder").textContent =
        "Camera unavailable — enter the collection token manually.";
      stopCamera();
    }
  }
  window.addEventListener("pagehide", stopCamera);
  startCamera();
})();
