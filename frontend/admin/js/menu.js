// Menu items: list, search and filter, create and edit, and availability. Categories come from the API.
(function () {
  "use strict";
  const P = window.adminPanel;
  const el = P.el;

  // Server field name -> form field name, for mapping validation errors back onto the form.
  const SERVER_TO_FORM = { price_paise: "price", stock_quantity: "stock", is_veg: "diet", recipe_steps: "recipe_steps" };
  const DIET_OPTIONS = [["", "Not recorded"], ["veg", "Vegetarian"], ["nonveg", "Non-vegetarian"]];

  function dietLabel(value) {
    if (value === true) return "Veg";
    if (value === false) return "Non-veg";
    return "Not recorded";
  }

  function stockText(item) {
    if (item.stock_quantity === null || item.stock_quantity === undefined) return "Not tracked";
    return item.available_quantity + " available · " + item.stock_quantity + " in stock";
  }

  function itemFormBody(item, categories) {
    const categoryOptions = categories.map((c) => [c.name, c.name]);
    const fields = {
      name: P.field({ label: "Name", name: "name", value: item ? item.name : "", maxLength: 120, required: true }),
      category: P.field({ label: "Category", name: "category", options: categoryOptions, value: item ? item.category : (categories[0] && categories[0].name) }),
      price: P.field({ label: "Price (₹)", name: "price", value: item ? (item.price_paise / 100).toFixed(2) : "", inputmode: "decimal", placeholder: "e.g. 45.00", required: true }),
      diet: P.field({ label: "Diet", name: "diet", options: DIET_OPTIONS, value: item ? (item.is_veg === true ? "veg" : item.is_veg === false ? "nonveg" : "") : "" }),
      stock: P.field({ label: "Stock quantity", name: "stock", type: "number", min: 0, max: 100000, step: 1, value: item && item.stock_quantity !== null ? item.stock_quantity : "", hint: "Leave empty to stop tracking stock." }),
      image_url: P.field({ label: "Image link", name: "image_url", type: "url", value: item ? (item.image_url || "") : "", maxLength: 500, hint: "Optional. An https link from an approved image host.", wide: true }),
      description: P.field({ label: "Description", name: "description", rows: 2, maxLength: 500, value: item ? (item.description || "") : "", wide: true }),
      ingredients: P.field({ label: "Ingredients", name: "ingredients", value: item ? (item.ingredients || []).join(", ") : "", hint: "Separate with commas.", wide: true }),
      recipe_steps: P.field({ label: "Preparation steps", name: "recipe_steps", rows: 3, value: item ? (item.recipe_steps || []).join("\n") : "", hint: "One step per line.", wide: true })
    };
    const available = el("input", { type: "checkbox", name: "is_available" });
    available.checked = item ? item.is_available : true;
    const availableRow = el("label", { class: "check field-wide" }, [available, el("span", { text: "Available to order" })]);
    const formFields = Object.values(fields);
    const form = el("form", { class: "form-grid", novalidate: true }, [
      ...formFields.map((f) => f.node),
      availableRow,
      el("div", { class: "form-actions field-wide" }, [])
    ]);
    return { form, fields: formFields, available, categoryField: fields.category };
  }

  function payloadFrom(form, available) {
    const data = P.readForm(form);
    const payload = {
      name: data.name.trim(),
      category: data.category,
      description: data.description.trim(),
      image_url: data.image_url.trim(),
      is_veg: data.diet === "veg" ? true : data.diet === "nonveg" ? false : null,
      ingredients: data.ingredients.split(",").map((s) => s.trim()).filter(Boolean),
      recipe_steps: data.recipe_steps.split("\n").map((s) => s.trim()).filter(Boolean),
      is_available: available.checked,
      stock_quantity: data.stock.trim() === "" ? null : Number(data.stock)
    };
    const paise = P.rupeesToPaise(data.price);
    payload.price_paise = paise === null ? undefined : paise;
    return payload;
  }

  function openEditor(item, categories, onSaved) {
    if (!categories.length) {
      P.modal({ title: "Create a category first", body: P.notice("Menu items belong to a category. Add one on the Categories page, then come back.", "info"), footer: el("a", { class: "btn btn-primary", href: "categories.html", text: "Go to categories" }) });
      return;
    }
    const built = itemFormBody(item, categories);
    const submit = el("button", { class: "btn btn-primary", type: "submit", text: item ? "Save changes" : "Add item" });
    const serverError = el("div", { class: "notice notice-danger", role: "alert", hidden: true });
    built.form.querySelector(".form-actions").append(
      el("button", { class: "btn btn-ghost", type: "button", text: "Cancel", onclick: () => dialog.close() }),
      submit
    );
    const dialog = P.modal({ title: item ? "Edit " + item.name : "Add a menu item", body: el("div", null, [serverError, built.form]), wide: true });

    built.form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = payloadFrom(built.form, built.available);
      const localErrors = {};
      if (payload.price_paise === undefined) localErrors.price = "Enter a price in rupees, for example 45 or 45.50.";
      if (payload.stock_quantity !== null && !Number.isInteger(payload.stock_quantity)) localErrors.stock = "Enter a whole number.";
      P.setFieldErrors(built.fields, localErrors);
      if (Object.keys(localErrors).length) return;

      submit.disabled = true;
      serverError.hidden = true;
      try {
        if (item) await trayApi.patch("/admin/menu/" + item.id, payload);
        else await trayApi.post("/admin/menu", payload);
        dialog.close();
        P.toast(item ? "Menu item saved." : "Menu item added.", "success");
        onSaved();
      } catch (error) {
        const details = {};
        Object.entries(P.fieldDetails(error)).forEach(([key, message]) => { details[SERVER_TO_FORM[key] || key] = message; });
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

  P.start({
    page: "menu",
    title: "Menu",
    run: async ({ content }) => {
      const state = { items: [], categories: [], query: "", category: "", availability: "" };
      const search = P.field({ label: "Search", name: "q", placeholder: "Item name or description", inputmode: "search" });
      search.node.classList.add("field-search");
      const categorySelect = P.field({ label: "Category", name: "category", options: [["", "All categories"]], value: "" });
      const availabilitySelect = P.field({ label: "Availability", name: "availability", options: [["", "All items"], ["yes", "Available"], ["no", "Unavailable"]], value: "" });
      const listBox = el("div");
      const addButton = el("button", { class: "btn btn-primary", type: "button", text: "Add item", onclick: () => openEditor(null, state.categories, reload) });

      content.replaceChildren(
        P.pageHead("Menu", "What students can order. Changes apply to the menu as soon as they are saved.", [addButton]),
        el("div", { class: "toolbar" }, [search.node, categorySelect.node, availabilitySelect.node]),
        el("div", { class: "card" }, [el("div", { class: "card-body", style: "padding:0" }, [listBox])])
      );
      search.input.addEventListener("input", () => { state.query = search.input.value.trim().toLowerCase(); render(); });
      categorySelect.input.addEventListener("change", () => { state.category = categorySelect.input.value; render(); });
      availabilitySelect.input.addEventListener("change", () => { state.availability = availabilitySelect.input.value; render(); });

      async function toggleAvailability(item) {
        try {
          await trayApi.patch("/admin/menu/" + item.id, { is_available: !item.is_available });
          P.toast(item.name + (item.is_available ? " is now unavailable." : " is now available."), "success");
          reload();
        } catch (error) {
          P.toast(P.describeError(error).text, "danger");
        }
      }

      function render() {
        const rows = state.items.filter((item) =>
          (!state.query || (item.name + " " + (item.description || "")).toLowerCase().includes(state.query)) &&
          (!state.category || item.category === state.category) &&
          (!state.availability || (state.availability === "yes") === Boolean(item.is_available)))
          .map((item) => [
            el("div", null, [
              el("div", { class: "cell-strong", text: item.name }),
              el("div", { class: "cell-muted", text: item.description || "No description" })
            ]),
            item.category,
            el("span", { class: "num", text: P.money(item.price_paise) }),
            el("span", { class: "cell-muted", text: stockText(item) }),
            el("span", { class: "cell-muted", text: dietLabel(item.is_veg) }),
            el("span", { class: "badge " + (item.is_available ? "badge-success" : "badge-muted"), text: item.is_available ? "Available" : "Unavailable" }),
            el("div", { class: "button-row" }, [
              el("button", { class: "btn btn-ghost btn-small", type: "button", text: "Edit", "aria-label": "Edit " + item.name, onclick: () => openEditor(item, state.categories, reload) }),
              el("button", { class: "btn btn-ghost btn-small", type: "button", text: item.is_available ? "Mark unavailable" : "Mark available", onclick: () => toggleAvailability(item) })
            ])
          ]);
        listBox.replaceChildren(P.table(
          [{ label: "Item" }, { label: "Category" }, { label: "Price", numeric: true }, { label: "Stock" }, { label: "Diet" }, { label: "Status" }, { label: "" }],
          rows,
          state.items.length ? "No items match these filters." : "No menu items yet. Add the first one."
        ));
      }

      async function reload() {
        listBox.replaceChildren(P.loading("Loading menu…"));
        try {
          const [menu, categories] = await Promise.all([trayApi.get("/admin/menu"), trayApi.get("/admin/categories")]);
          state.items = P.unwrap(menu).items || menu.items || [];
          state.categories = P.unwrap(categories).categories || [];
          categorySelect.input.replaceChildren(
            el("option", { value: "", text: "All categories" }),
            ...state.categories.map((c) => el("option", { value: c.name, text: c.name, selected: c.name === state.category }))
          );
          render();
        } catch (error) {
          listBox.replaceChildren(P.errorNotice(error));
        }
      }

      reload();
    }
  });
})();
