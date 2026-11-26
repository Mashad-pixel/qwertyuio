(function () {
  "use strict";

  document.getElementById("app-header").innerHTML = trayComponents.header("My Orders");

  // Only known student pages may be used as a return destination. This prevents open redirects.
  const RETURN_PAGES = { "checkout.html": "./checkout.html", "cart.html": "./cart.html" };
  const params = new URLSearchParams(window.location.search);
  const returnTo = RETURN_PAGES[params.get("next")] || "../index.html";

  const $ = (id) => document.getElementById(id);
  const tabLogin = $("tab-login");
  const tabRegister = $("tab-register");
  const loginForm = $("login-form");
  const registerForm = $("register-form");

  function showTab(which) {
    const loginActive = which === "login";
    loginForm.hidden = !loginActive;
    registerForm.hidden = loginActive;
    tabLogin.setAttribute("aria-selected", String(loginActive));
    tabRegister.setAttribute("aria-selected", String(!loginActive));
  }
  tabLogin.addEventListener("click", () => showTab("login"));
  tabRegister.addEventListener("click", () => showTab("register"));

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = $("login-email").value.trim();
    const password = $("login-password").value;
    if (!trayValidation.email(email) || !password) {
      trayNotify("Enter a valid email and password");
      return;
    }
    try {
      const response = await trayAuth.login(email, password);
      if (String(response?.data?.role || "").toUpperCase() === "STUDENT") {
        window.location.href = returnTo;
        return;
      }
      // A staff account signed in here. Sign it out so staff and students are kept separate.
      await trayAuth.logout().catch(() => {});
      trayNotify("This is a staff account. Use the staff sign-in page.");
    } catch (error) {
      trayNotify(error.status === 429 ? "Too many attempts. Wait a few minutes and try again." : (error.message || "Unable to log in"));
    }
  });

  registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = $("register-name").value.trim();
    const email = $("register-email").value.trim();
    const password = $("register-password").value;
    if (!name) { trayNotify("Enter your name"); return; }
    if (!trayValidation.email(email)) { trayNotify("Enter a valid email address"); return; }
    if (password.length < 8) { trayNotify("Password must be at least 8 characters"); return; }

    try {
      await trayApi.post("/auth/register", { name, email, password });
      window.location.href = returnTo;
    } catch (error) {
      trayNotify(error.status === 429 ? "Too many attempts. Wait a few minutes and try again." : (error.message || "Could not create the account"));
    }
  });
})();
