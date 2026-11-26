// Canteen details, ordering on/off, and the administrator's own account: email, password,
// two-factor status and active sessions. Every change is saved by the server and reported back here.
(function () {
  "use strict";
  const P = window.adminPanel;
  const el = P.el;
  const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

  function passwordStrengthProblem(value) {
    if (value.length < 8) return "Use at least 8 characters.";
    if (value.length > 128) return "Use at most 128 characters.";
    if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) return "Include at least one letter and one number.";
    return "";
  }

  function formatDetails(error) {
    const details = P.fieldDetails(error);
    return details;
  }

  P.start({
    page: "settings",
    title: "Settings",
    run: async ({ content, user }) => {
      content.replaceChildren(
        P.pageHead("Settings", "Canteen details, ordering, and the security of your administrator account."),
        P.loading("Loading settings…")
      );

      let settings;
      let account;
      try {
        const [settingsRes, accountRes] = await Promise.all([
          trayApi.get("/admin/canteen/settings"),
          trayApi.get("/account")
        ]);
        settings = P.unwrap(settingsRes);
        account = P.unwrap(accountRes);
      } catch (error) {
        content.replaceChildren(P.pageHead("Settings", ""), P.errorNotice(error));
        return;
      }

      const canteenCard = buildCanteenCard(settings);
      const statusCard = buildStatusCard(settings);
      const profileCard = buildProfileCard(account);
      const emailCard = buildEmailCard(account);
      const passwordCard = buildPasswordCard();
      const sessionsCard = buildSessionsCard();

      content.replaceChildren(
        P.pageHead("Settings", "Canteen details, ordering, and the security of your administrator account."),
        el("div", { class: "grid grid-2" }, [canteenCard.node, statusCard.node]),
        el("h2", { class: "section-heading", text: "Your account" }),
        el("div", { class: "grid grid-2" }, [profileCard, emailCard.node, passwordCard.node]),
        el("div", { style: "margin-top:18px" }, [sessionsCard.node])
      );
      sessionsCard.load();

      function buildCanteenCard(current) {
        const name = P.field({ label: "Canteen name", name: "canteen_name", value: current.canteen_name, maxLength: 80, required: true, wide: true, hint: "Shown to students on the menu." });
        const opens = P.field({ label: "Opens at", name: "opens_at", type: "time", value: current.opens_at || "" });
        const closes = P.field({ label: "Closes at", name: "closes_at", type: "time", value: current.closes_at || "" });
        const notice = el("div", { class: "field-error", role: "alert", hidden: true, style: "grid-column:1/-1" });
        const submit = el("button", { class: "btn btn-primary", type: "submit", text: "Save details" });
        const form = el("form", { class: "form-grid", novalidate: true }, [
          name.node, opens.node, closes.node,
          el("p", { class: "field-hint", style: "grid-column:1/-1", text: "Leave both times empty to hide opening hours from students." }),
          notice,
          el("div", { class: "form-actions field-wide" }, [submit])
        ]);
        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          const local = {};
          if (!name.input.value.trim()) local.canteen_name = "Enter the canteen name.";
          if (opens.input.value && !HHMM.test(opens.input.value)) local.opens_at = "Use 24-hour time.";
          if (closes.input.value && !HHMM.test(closes.input.value)) local.closes_at = "Use 24-hour time.";
          P.setFieldErrors([name, opens, closes], local);
          if (Object.keys(local).length) return;
          submit.disabled = true;
          notice.hidden = true;
          try {
            const saved = P.unwrap(await trayApi.patch("/admin/canteen/settings", {
              canteen_name: name.input.value,
              opens_at: opens.input.value || null,
              closes_at: closes.input.value || null
            }));
            Object.assign(settings, saved);
            P.toast("Canteen details saved.", "success");
          } catch (error) {
            const details = formatDetails(error);
            P.setFieldErrors([name, opens, closes], details);
            if (details.hours) { notice.textContent = details.hours; notice.hidden = false; }
            else if (!Object.keys(details).length) { notice.textContent = P.describeError(error).text; notice.hidden = false; }
          } finally {
            submit.disabled = false;
          }
        });
        return { node: P.card({ title: "Canteen details", subtitle: "Name and opening hours students see", body: form }) };
      }

      function buildStatusCard(current) {
        const open = current.is_accepting_orders;
        const toggle = el("button", { class: "btn " + (open ? "btn-danger" : "btn-primary"), type: "button", text: open ? "Pause orders" : "Resume orders" });
        const card = P.card({
          title: "Ordering",
          subtitle: "Whether students can place new orders right now",
          body: el("div", { class: "stack" }, [
            el("div", { class: "status-tile" }, [
              el("span", { text: "Current state" }),
              el("span", { class: "badge " + (open ? "badge-success" : "badge-danger"), text: open ? "Accepting orders" : "Orders paused" })
            ]),
            !open && current.closed_message ? P.notice("Message shown to students: " + current.closed_message, "warning") : null,
            el("div", { class: "button-row" }, [toggle])
          ])
        });
        toggle.addEventListener("click", () => (open ? pauseDialog() : resume()));

        function pauseDialog() {
          const message = P.field({ label: "Message for students (optional)", name: "closed_message", rows: 3, maxLength: 200, value: "", hint: "For example: Closed for stock-taking until 3 pm." });
          const submit = el("button", { class: "btn btn-danger", type: "submit", text: "Pause orders" });
          const form = el("form", { class: "stack", novalidate: true }, [message.node]);
          const dialog = P.modal({
            title: "Pause ordering?",
            body: form,
            footer: el("div", { class: "button-row" }, [el("button", { class: "btn btn-ghost", type: "button", text: "Cancel", onclick: () => dialog.close() }), submit])
          });
          form.addEventListener("submit", async (event) => {
            event.preventDefault();
            submit.disabled = true;
            try {
              await trayApi.patch("/admin/canteen/status", { is_accepting_orders: false, closed_message: message.input.value.trim() || null });
              dialog.close();
              P.toast("Ordering is paused.", "success");
              window.location.reload();
            } catch (error) {
              P.toast(P.describeError(error).text, "danger");
              submit.disabled = false;
            }
          });
        }

        async function resume() {
          try {
            await trayApi.patch("/admin/canteen/status", { is_accepting_orders: true });
            P.toast("Ordering is open again.", "success");
            window.location.reload();
          } catch (error) {
            P.toast(P.describeError(error).text, "danger");
          }
        }

        return { node: card };
      }

      function buildProfileCard(acct) {
        return P.card({
          title: "Administrator account",
          body: P.keyValues([
            ["Name", acct.name],
            ["Role", user.role === "ADMIN" ? "Administrator" : user.role],
            ["Two-factor", el("span", { class: "badge " + (acct.mfa_enabled ? "badge-success" : "badge-danger"), text: acct.mfa_enabled ? "On" : "Not set up" })],
            ["Password changed", acct.password_changed_at ? P.formatDateTime(acct.password_changed_at) : "Not changed since the account was created"]
          ])
        });
      }

      function buildEmailCard(acct) {
        const current = P.field({ label: "Current password", name: "current_password", type: "password", autocomplete: "current-password", maxLength: 128, required: true });
        const newEmail = P.field({ label: "New sign-in email", name: "new_email", type: "email", autocomplete: "email", maxLength: 120, required: true });
        const notice = el("div", { class: "field-error", role: "alert", hidden: true });
        const submit = el("button", { class: "btn btn-primary", type: "submit", text: "Change email" });
        const emailNow = el("strong", { text: acct.email });
        const form = el("form", { class: "stack", novalidate: true }, [
          el("p", { class: "cell-muted", style: "margin:0" }, ["Currently: ", emailNow]),
          current.node, newEmail.node, notice,
          el("div", { class: "form-actions" }, [submit])
        ]);
        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          notice.hidden = true;
          const local = {};
          if (!current.input.value) local.current_password = "Enter your current password.";
          if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(newEmail.input.value.trim())) local.new_email = "Enter a valid email address.";
          P.setFieldErrors([current, newEmail], local);
          if (Object.keys(local).length) return;
          submit.disabled = true;
          try {
            const result = P.unwrap(await trayApi.post("/account/email", {
              current_password: current.input.value, new_email: newEmail.input.value.trim()
            }));
            emailNow.textContent = result.email;
            current.input.value = "";
            newEmail.input.value = "";
            P.toast("Sign-in email changed. Other devices were signed out.", "success");
            sessionsCard.load();
          } catch (error) {
            const details = formatDetails(error);
            P.setFieldErrors([current, newEmail], details);
            if (!Object.keys(details).length) { notice.textContent = P.describeError(error).text; notice.hidden = false; }
          } finally {
            submit.disabled = false;
          }
        });
        return { node: P.card({ title: "Change sign-in email", subtitle: "Confirm with your current password. Your other sessions are signed out.", body: form }) };
      }

      function buildPasswordCard() {
        const current = P.field({ label: "Current password", name: "current_password", type: "password", autocomplete: "current-password", maxLength: 128, required: true });
        const next = P.field({ label: "New password", name: "new_password", type: "password", autocomplete: "new-password", maxLength: 128, required: true, hint: "At least 8 characters, with a letter and a number." });
        const confirm = P.field({ label: "Confirm new password", name: "confirm_password", type: "password", autocomplete: "new-password", maxLength: 128, required: true });
        const notice = el("div", { class: "field-error", role: "alert", hidden: true });
        const submit = el("button", { class: "btn btn-primary", type: "submit", text: "Change password" });
        const form = el("form", { class: "stack", novalidate: true }, [current.node, next.node, confirm.node, notice, el("div", { class: "form-actions" }, [submit])]);
        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          notice.hidden = true;
          const local = {};
          if (!current.input.value) local.current_password = "Enter your current password.";
          const problem = passwordStrengthProblem(next.input.value);
          if (problem) local.new_password = problem;
          if (confirm.input.value !== next.input.value) local.confirm_password = "The passwords do not match.";
          P.setFieldErrors([current, next, confirm], local);
          if (Object.keys(local).length) return;
          submit.disabled = true;
          try {
            const result = P.unwrap(await trayApi.post("/account/password", {
              current_password: current.input.value, new_password: next.input.value
            }));
            current.input.value = "";
            next.input.value = "";
            confirm.input.value = "";
            P.toast(result.signed_out_other_sessions
              ? "Password changed. " + result.signed_out_other_sessions + " other session(s) signed out."
              : "Password changed.", "success");
            sessionsCard.load();
          } catch (error) {
            const details = formatDetails(error);
            P.setFieldErrors([current, next, confirm], details);
            if (!Object.keys(details).length) { notice.textContent = P.describeError(error).text; notice.hidden = false; }
          } finally {
            submit.disabled = false;
          }
        });
        return { node: P.card({ title: "Change password", subtitle: "Changing it signs out every other session.", body: form }) };
      }

      function buildSessionsCard() {
        const box = el("div", null, [P.loading("Loading sessions…")]);
        const signOut = el("button", { class: "btn btn-danger btn-small", type: "button", text: "Sign out other sessions" });
        async function load() {
          box.replaceChildren(P.loading("Loading sessions…"));
          try {
            const data = P.unwrap(await trayApi.get("/account/sessions"));
            const sessions = data.sessions || [];
            box.replaceChildren(P.table(
              [{ label: "Started" }, { label: "Last active" }, { label: "Expires" }, { label: "Two-factor" }, { label: "" }],
              sessions.map((s) => [
                el("span", { class: "cell-muted", text: P.formatDateTime(s.created_at) }),
                el("span", { class: "cell-muted", text: P.formatDateTime(s.last_seen_at) }),
                el("span", { class: "cell-muted", text: P.formatDateTime(s.expires_at) }),
                el("span", { class: "badge " + (s.mfa_verified ? "badge-success" : "badge-warning"), text: s.mfa_verified ? "Verified" : "Pending" }),
                s.current ? el("span", { class: "badge badge-info", text: "This device" }) : el("span", { class: "cell-muted", text: "Other device" })
              ]),
              "No active sessions."
            ));
            signOut.disabled = sessions.filter((s) => !s.current).length === 0;
          } catch (error) {
            box.replaceChildren(P.errorNotice(error));
          }
        }
        signOut.addEventListener("click", async () => {
          const confirmed = await P.confirmAction({
            title: "Sign out other sessions?",
            message: "Every other browser or device signed in to this account will be signed out. This device stays signed in.",
            confirmLabel: "Sign out others",
            danger: true
          });
          if (!confirmed) return;
          try {
            const result = P.unwrap(await trayApi.post("/account/sessions/revoke-others", {}));
            P.toast(result.revoked + " other session(s) signed out.", "success");
            load();
          } catch (error) {
            P.toast(P.describeError(error).text, "danger");
          }
        });
        const node = P.card({
          title: "Active sessions",
          subtitle: "Where your account is signed in right now",
          actions: [signOut],
          body: box
        });
        return { node, load };
      }
    }
  });
})();
