// Staff accounts (administrators and kitchen). The server enforces every rule; this page shows its answers.
(function () {
  "use strict";
  const P = window.adminPanel;
  const el = P.el;
  const ROLE_OPTIONS = [["KITCHEN", "Kitchen staff"], ["ADMIN", "Administrator"]];

  function staffForm(member, currentUserId) {
    const fields = [];
    const name = P.field({ label: "Full name", name: "name", value: member ? member.name : "", maxLength: 100, required: true });
    const email = P.field({ label: "Sign-in email", name: "email", type: "email", value: member ? member.email : "", maxLength: 120, required: !member, disabled: Boolean(member), hint: member ? "Email addresses cannot be changed here." : null });
    const role = P.field({ label: "Role", name: "role", options: ROLE_OPTIONS, value: member ? member.role : "KITCHEN" });
    const password = P.field({
      label: member ? "New password (optional)" : "Password",
      name: "password", type: "password", autocomplete: "new-password", maxLength: 128, required: !member,
      hint: "At least 8 characters, with a letter and a number. Setting a new password signs the account out everywhere."
    });
    fields.push(name, email, role, password);
    const active = el("input", { type: "checkbox", name: "is_active" });
    active.checked = member ? member.is_active : true;
    const activeRow = member && member.id !== currentUserId
      ? el("label", { class: "check field-wide" }, [active, el("span", { text: "Account is active (can sign in)" })])
      : null;
    const hint = member
      ? null
      : P.notice("Administrators must set up two-factor authentication the first time they sign in. Kitchen staff sign in with email and password.", "info");
    const form = el("form", { class: "form-grid", novalidate: true }, [
      hint ? el("div", { class: "field-wide" }, [hint]) : null,
      ...fields.map((f) => f.node),
      activeRow
    ]);
    return { form, fields, active, password };
  }

  P.start({
    page: "staff",
    title: "Staff",
    run: ({ content, user }) => {
      const listBox = el("div");
      const addButton = el("button", { class: "btn btn-primary", type: "button", text: "Add staff account", onclick: () => openEditor(null) });
      content.replaceChildren(
        P.pageHead("Staff", "Administrator and kitchen accounts. Students register themselves and are not listed here.", [addButton]),
        P.card({ body: listBox })
      );

      function openEditor(member) {
        const built = staffForm(member, user.id);
        const serverError = el("div", { class: "notice notice-danger", role: "alert", hidden: true });
        const submit = el("button", { class: "btn btn-primary", type: "submit", text: member ? "Save changes" : "Create account" });
        built.form.append(el("div", { class: "form-actions field-wide" }, [
          el("button", { class: "btn btn-ghost", type: "button", text: "Cancel", onclick: () => dialog.close() }),
          submit
        ]));
        const dialog = P.modal({
          title: member ? "Edit " + member.name : "Add a staff account",
          body: el("div", null, [serverError, built.form]),
          wide: true
        });

        built.form.addEventListener("submit", async (event) => {
          event.preventDefault();
          const data = P.readForm(built.form);
          const localErrors = {};
          if (!member && !data.email.trim()) localErrors.email = "Enter an email address.";
          if (data.password && data.password.length < 8) localErrors.password = "Use at least 8 characters.";
          P.setFieldErrors(built.fields, localErrors);
          if (Object.keys(localErrors).length) return;

          submit.disabled = true;
          serverError.hidden = true;
          try {
            if (member) {
              const payload = { name: data.name.trim(), role: data.role };
              if (member.id !== user.id) payload.is_active = built.active.checked;
              if (data.password) payload.password = data.password;
              await trayApi.patch("/admin/staff/" + member.id, payload);
              P.toast("Staff account saved.", "success");
            } else {
              await trayApi.post("/admin/staff", {
                name: data.name.trim(), email: data.email.trim(), role: data.role, password: data.password
              });
              P.toast("Staff account created.", "success");
            }
            dialog.close();
            load();
          } catch (error) {
            const details = P.fieldDetails(error);
            P.setFieldErrors(built.fields, details);
            if (!Object.keys(details).length) {
              serverError.textContent = P.describeError(error).text;
              serverError.hidden = false;
            }
            submit.disabled = false;
          }
        });
        built.fields[0].input.focus();
      }

      async function toggleActive(member) {
        const next = !member.is_active;
        const confirmed = await P.confirmAction({
          title: (next ? "Reactivate " : "Deactivate ") + member.name + "?",
          message: next
            ? "They will be able to sign in again."
            : "They will be signed out immediately and cannot sign in until reactivated.",
          confirmLabel: next ? "Reactivate" : "Deactivate",
          danger: !next
        });
        if (!confirmed) return;
        try {
          await trayApi.patch("/admin/staff/" + member.id, { is_active: next });
          P.toast(member.name + (next ? " is active again." : " has been deactivated."), "success");
          load();
        } catch (error) {
          P.toast(P.describeError(error).text, "danger");
        }
      }

      async function load() {
        listBox.replaceChildren(P.loading("Loading staff…"));
        try {
          const data = P.unwrap(await trayApi.get("/admin/staff"));
          const staff = data.staff || [];
          listBox.replaceChildren(P.table(
            [{ label: "Name" }, { label: "Role" }, { label: "Status" }, { label: "Added" }, { label: "" }],
            staff.map((member) => [
              el("div", null, [
                el("div", { class: "cell-strong", text: member.name + (member.id === user.id ? " (you)" : "") }),
                el("div", { class: "cell-muted", text: member.email })
              ]),
              el("span", { class: "badge " + (member.role === "ADMIN" ? "badge-info" : "badge-muted"), text: member.role === "ADMIN" ? "Administrator" : "Kitchen" }),
              el("span", { class: "badge " + (member.is_active ? "badge-success" : "badge-danger"), text: member.is_active ? "Active" : "Deactivated" }),
              el("span", { class: "cell-muted", text: P.formatDateTime(member.created_at) }),
              el("div", { class: "button-row" }, [
                el("button", { class: "btn btn-ghost btn-small", type: "button", text: "Edit", "aria-label": "Edit " + member.name, onclick: () => openEditor(member) }),
                member.id === user.id ? null : el("button", {
                  class: "btn btn-small " + (member.is_active ? "btn-danger" : "btn-ghost"), type: "button",
                  text: member.is_active ? "Deactivate" : "Reactivate", onclick: () => toggleActive(member)
                })
              ])
            ]),
            "No staff accounts yet."
          ));
        } catch (error) {
          listBox.replaceChildren(P.errorNotice(error));
        }
      }

      load();
    }
  });
})();
