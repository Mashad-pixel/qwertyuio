(function () {
  const form = document.getElementById("login-form");
  const submit = form.querySelector('button[type="submit"]');
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    if (!trayValidation.email(email) || !password) {
      trayNotify("Enter a valid email and password."); return;
    }
    submit.disabled = true;
    try {
      const response = await trayAuth.login(email, password);
      const role = response?.data?.role;
      if (role === "KITCHEN") window.location.href = "./dashboard.html";
      else if (role === "ADMIN") window.location.href = "../admin/dashboard.html";
      else trayNotify("This account does not have kitchen access.");
    } catch (error) {
      // Failed authentication must never create a local demo role.
      trayNotify(error.message || "Unable to sign in.");
    } finally { submit.disabled = false; }
  });
})();
