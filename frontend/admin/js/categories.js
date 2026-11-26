// Menu categories: create, rename (moves its items), and delete when no item uses it.
(function () {
  "use strict";
  const P = window.adminPanel;
  const el = P.el;

  function renameDialog(category, onDone) {
    const name = P.field({ label: "Category name", name: "name", value: category.name, maxLength: 60, required: true, hint: "Menu items in this category move to the new name." });
    const error = el("div", { class: "field-error", role: "alert", hidden: true });
    const submit = el("button", { class: "btn btn-primary", type: "submit", text: "Save name" });
    const form = el("form", { class: "stack", novalidate: true }, [name.node, error]);
    const dialog = P.modal({
      title: "Rename " + category.name,
      body: form,
      footer: el("div", { class: "button-row" }, [el("button", { class: "btn btn-ghost", type: "button", text: "Cancel", onclick: () => dialog.close() }), submit])
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        await trayApi.patch("/admin/categories/" + category.id, { name: name.input.value });
        dialog.close();
        P.toast("Category renamed.", "success");
        onDone();
      } catch (err) {
        const details = P.fieldDetails(err);
        P.setFieldErrors([name], details);
        if (!details.name) { error.textContent = P.describeError(err).text; error.hidden = false; }
        submit.disabled = false;
      }
    });
    name.input.focus();
    name.input.select();
  }

  async function remove(category, onDone) {
    const confirmed = await P.confirmAction({
      title: "Delete " + category.name + "?",
      message: "The category will be removed. This cannot be undone.",
      confirmLabel: "Delete category",
      danger: true
    });
    if (!confirmed) return;
    try {
      await trayApi.del("/admin/categories/" + category.id);
      P.toast("Category deleted.", "success");
      onDone();
    } catch (error) {
      P.toast(P.describeError(error).text, "danger");
    }
  }

  P.start({
    page: "categories",
    title: "Categories",
    run: ({ content }) => {
      const createName = P.field({ label: "New category", name: "name", placeholder: "e.g. Beverages", maxLength: 60, required: true, wide: false });
      const createError = el("div", { class: "field-error", role: "alert", hidden: true });
      const createForm = el("form", { class: "toolbar", novalidate: true }, [
        createName.node,
        el("button", { class: "btn btn-primary", type: "submit", text: "Add category" })
      ]);
      const listBox = el("div");

      content.replaceChildren(
        P.pageHead("Categories", "Groups that menu items are sorted into. Each item must belong to one category."),
        P.card({ body: [createForm, createError] }),
        el("div", { style: "margin-top:18px" }, [listBox])
      );

      createForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        createError.hidden = true;
        const value = createName.input.value.trim();
        if (!value) { createError.textContent = "Enter a name for the category."; createError.hidden = false; return; }
        const button = createForm.querySelector("button");
        button.disabled = true;
        try {
          await trayApi.post("/admin/categories", { name: value });
          createName.input.value = "";
          P.toast("Category added.", "success");
          load();
        } catch (error) {
          const details = P.fieldDetails(error);
          createError.textContent = details.name || P.describeError(error).text;
          createError.hidden = false;
        } finally {
          button.disabled = false;
        }
      });

      async function load() {
        listBox.replaceChildren(P.loading("Loading categories…"));
        try {
          const data = P.unwrap(await trayApi.get("/admin/categories"));
          const categories = data.categories || [];
          listBox.replaceChildren(P.card({
            body: P.table(
              [{ label: "Name" }, { label: "Menu items", numeric: true }, { label: "" }],
              categories.map((category) => [
                el("span", { class: "cell-strong", text: category.name }),
                el("span", { class: "num", text: String(category.item_count) }),
                el("div", { class: "button-row" }, [
                  el("button", { class: "btn btn-ghost btn-small", type: "button", text: "Rename", "aria-label": "Rename " + category.name, onclick: () => renameDialog(category, load) }),
                  el("button", {
                    class: "btn btn-danger btn-small", type: "button", text: "Delete",
                    disabled: category.item_count > 0,
                    title: category.item_count > 0 ? "Move or delete its items first." : null,
                    "aria-label": "Delete " + category.name,
                    onclick: () => remove(category, load)
                  })
                ])
              ]),
              "No categories yet. Add one above."
            )
          }));
        } catch (error) {
          listBox.replaceChildren(P.errorNotice(error));
        }
      }

      load();
    }
  });
})();
