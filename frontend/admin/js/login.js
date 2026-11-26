(function () {
  "use strict";

  const cards = { login: document.getElementById("card-login"), mfa: document.getElementById("card-mfa"), setup: document.getElementById("card-setup") };
  const loginForm = document.getElementById("login-form");
  const mfaForm = document.getElementById("mfa-form");
  const setupForm = document.getElementById("setup-form");
  const loginError = document.getElementById("login-error");
  const mfaError = document.getElementById("mfa-error");
  const setupError = document.getElementById("setup-error");
  const setupSecret = document.getElementById("setup-secret");
  const setupLink = document.getElementById("setup-link");
  const emailPattern = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

  // Role returned by the password step. Kept so the setup step can send the user to the right place.
  let pendingRole = null;

  function show(name) {
    Object.entries(cards).forEach(([key, card]) => { card.hidden = key !== name; });
  }

  function setError(node, text) {
    node.textContent = text || "";
    node.hidden = !text;
  }

  function busy(form, isBusy) {
    form.querySelector("button[type='submit']").disabled = isBusy;
  }

  function goToDashboard(role) {
    if (role === "ADMIN") window.location.replace("dashboard.html");
    else if (role === "KITCHEN") window.location.replace("../kitchen/dashboard.html");
    else setError(loginError, "This account does not have administrator access.");
  }

  async function startSetup() {
    const response = await trayApi.post("/auth/mfa/setup", {});
    const setup = (response && response.data) || {};
    // Server values are written as text. The link only accepts otpauth:// URIs.
    setupSecret.textContent = typeof setup.secret === "string" ? setup.secret : "";
    if (typeof setup.otpauth_uri === "string" && setup.otpauth_uri.startsWith("otpauth://")) {
      setupLink.href = setup.otpauth_uri;
      setupLink.hidden = false;
    } else {
      setupLink.hidden = true;
    }
    show("setup");
    document.getElementById("setup-code").focus();
  }

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setError(loginError, "");
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    if (!emailPattern.test(email) || !password) {
      setError(loginError, "Enter a valid email and password.");
      return;
    }
    busy(loginForm, true);
    try {
      const response = await trayAuth.login(email, password);
      const data = (response && response.data) || {};
      pendingRole = data.role || null;
      if (data.mfa_required) {
        show("mfa");
        document.getElementById("mfa-code").focus();
      } else if (data.mfa_setup_required) {
        await startSetup();
      } else {
        goToDashboard(data.role);
      }
    } catch (error) {
      setError(loginError, error.status === 429
        ? "Too many sign-in attempts. Wait a few minutes and try again."
        : (error.message || "Unable to sign in."));
    } finally {
      busy(loginForm, false);
    }
  });

  mfaForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setError(mfaError, "");
    busy(mfaForm, true);
    try {
      const code = document.getElementById("mfa-code").value.replace(/\s/g, "");
      const response = await trayApi.post("/auth/mfa/verify", { code });
      goToDashboard((response && response.data && response.data.role) || pendingRole);
    } catch (error) {
      setError(mfaError, error.message || "Unable to verify the code.");
    } finally {
      busy(mfaForm, false);
    }
  });

  setupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setError(setupError, "");
    busy(setupForm, true);
    try {
      const code = document.getElementById("setup-code").value.replace(/\s/g, "");
      await trayApi.post("/auth/mfa/confirm", { code });
      goToDashboard(pendingRole);
    } catch (error) {
      setError(setupError, error.message || "Unable to turn on two-factor authentication.");
    } finally {
      busy(setupForm, false);
    }
  });

  document.getElementById("email").focus();
})();
