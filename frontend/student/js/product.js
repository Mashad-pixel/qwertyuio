(function () {
  const productId = Number(new URLSearchParams(window.location.search).get("id"));
  document.getElementById("app-header").innerHTML = trayComponents.header();

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;"
    })[character]);
  }

  function croppedImage(source, crop) {
    try {
      const url = new URL(source, window.location.href);
      url.searchParams.set("w", "1100");
      url.searchParams.set("h", "900");
      url.searchParams.set("fit", "crop");
      url.searchParams.set("crop", crop);
      return url.toString();
    } catch {
      return source;
    }
  }

  function setSectionVisible(element, visible) {
    const section = element.closest("section") || element;
    section.hidden = !visible;
  }

  function cartCount() {
    return trayStorage.getCart().reduce((sum, item) => sum + Number(item.qty || 0), 0);
  }

  function addProductToCart(product) {
    const cart = trayStorage.getCart();
    const existing = cart.find((item) => item.id === product.id);
    if (existing) existing.qty += 1;
    else cart.push({ id: product.id, name: product.name, price: product.price, image: product.image, qty: 1 });
    trayStorage.set("trayup-cart", cart);
    document.getElementById("cart-count").textContent = cartCount();
  }

  function renderProduct(product, all) {
    const galleryViews = product.image
      ? [
        { label: "Full view", image: product.image },
        { label: "Close-up", image: croppedImage(product.image, "center") },
        { label: "Dish detail", image: croppedImage(product.image, "entropy") }
      ]
      : [];
    const galleryTrack = document.getElementById("product-gallery-track");
    const thumbnails = document.getElementById("product-gallery-thumbnails");
    let activeImage = 0;

    document.title = `${product.name} — TrayUP`;
    document.getElementById("product-category").textContent = product.category;
    document.getElementById("breadcrumb-name").textContent = product.name;
    document.getElementById("product-category-label").textContent = product.category;
    // The backend does not record ratings yet, so the rating badge stays hidden.
    document.getElementById("product-rating").hidden = true;
    document.getElementById("product-name").textContent = product.name;
    document.getElementById("story-product-name").textContent = product.name;
    document.getElementById("product-description").textContent = product.description;

    const dot = document.getElementById("product-diet-dot");
    dot.classList.remove("is-veg", "is-non-veg");
    if (product.hasDiet) dot.classList.add(product.isVeg ? "is-veg" : "is-non-veg");
    const dietText = product.hasDiet ? (product.isVeg ? "Vegetarian" : "Non-vegetarian") : "Diet not recorded";
    document.getElementById("product-availability").textContent =
      `${dietText} · ${product.isAvailable ? "Available now" : "Currently unavailable"}`;
    document.getElementById("product-price").textContent = `₹${Number(product.price).toLocaleString("en-IN")}`;

    // Only show the story sections that have recorded content.
    const historyEl = document.getElementById("product-history");
    historyEl.hidden = true;
    const ingredientsEl = document.getElementById("product-ingredients");
    ingredientsEl.innerHTML = product.ingredients.map((ingredient) => `<li>${escapeHtml(ingredient)}</li>`).join("");
    setSectionVisible(ingredientsEl, product.ingredients.length > 0);
    const preparationEl = document.getElementById("product-preparation");
    preparationEl.textContent = product.preparation;
    setSectionVisible(preparationEl, Boolean(product.preparation));
    const hasStory = product.ingredients.length > 0 || Boolean(product.preparation) || product.recipeSteps.length > 0;
    const storyEl = document.querySelector(".product-story");
    if (storyEl) storyEl.hidden = !hasStory;

    const recipeSection = document.getElementById("product-recipe-section");
    if (product.recipeSteps.length) {
      document.getElementById("product-recipe-steps").innerHTML =
        product.recipeSteps.map((step) => `<li>${escapeHtml(step)}</li>`).join("");
      recipeSection.hidden = false;
    } else {
      recipeSection.hidden = true;
    }

    const helpButton = document.getElementById("product-help-button");
    const helpDetails = document.getElementById("product-help-details");
    helpButton.addEventListener("click", () => {
      const expanded = helpButton.getAttribute("aria-expanded") === "true";
      helpButton.setAttribute("aria-expanded", String(!expanded));
      helpDetails.hidden = expanded;
      helpButton.textContent = expanded ? "Show help" : "Hide help";
    });

    // Images that fail to load are hidden by the shared error listener, not by inline handlers.
    galleryTrack.innerHTML = galleryViews.map((view, index) => `
      <figure class="product-gallery-slide">
        <img src="${escapeHtml(view.image)}" alt="${escapeHtml(product.name)} — ${escapeHtml(view.label)}" loading="eager" data-hide-on-error ${index ? "" : "fetchpriority=\"high\""}>
        <figcaption>${escapeHtml(view.label)}</figcaption>
      </figure>
    `).join("");
    thumbnails.innerHTML = galleryViews.map((view, index) => `
      <button class="product-gallery-thumbnail${index === 0 ? " active" : ""}" type="button" data-gallery-index="${index}" aria-label="${escapeHtml(view.label)}" aria-pressed="${index === 0}">
        <img src="${escapeHtml(view.image)}" alt="" loading="eager" data-hide-on-error>
      </button>
    `).join("");

    function updateGallery(index) {
      activeImage = Math.max(0, Math.min(galleryViews.length - 1, index));
      galleryTrack.scrollTo({ left: activeImage * galleryTrack.clientWidth, behavior: "smooth" });
      thumbnails.querySelectorAll("[data-gallery-index]").forEach((button, buttonIndex) => {
        button.classList.toggle("active", buttonIndex === activeImage);
        button.setAttribute("aria-pressed", String(buttonIndex === activeImage));
      });
    }

    galleryTrack.addEventListener("scroll", () => {
      if (!galleryTrack.clientWidth) return;
      const index = Math.round(galleryTrack.scrollLeft / galleryTrack.clientWidth);
      if (index === activeImage || index < 0 || index >= galleryViews.length) return;
      activeImage = index;
      thumbnails.querySelectorAll("[data-gallery-index]").forEach((button, buttonIndex) => {
        button.classList.toggle("active", buttonIndex === activeImage);
        button.setAttribute("aria-pressed", String(buttonIndex === activeImage));
      });
    }, { passive: true });

    thumbnails.addEventListener("click", (event) => {
      const button = event.target.closest("[data-gallery-index]");
      if (button) updateGallery(Number(button.dataset.galleryIndex));
    });
    document.querySelector("[data-gallery-previous]").addEventListener("click", () => updateGallery(activeImage - 1));
    document.querySelector("[data-gallery-next]").addEventListener("click", () => updateGallery(activeImage + 1));

    document.getElementById("add-product").addEventListener("click", () => {
      if (!product.isAvailable) return;
      addProductToCart(product);
      trayNotify(`${product.name} added to your cart`);
    });
    document.getElementById("order-product").addEventListener("click", () => {
      if (!product.isAvailable) return;
      addProductToCart(product);
      window.location.href = "./checkout.html";
    });
    document.getElementById("add-product").disabled = !product.isAvailable;
    document.getElementById("order-product").disabled = !product.isAvailable;

    document.getElementById("cart-count").textContent = cartCount();
    document.getElementById("open-cart").addEventListener("click", () => {
      window.location.href = "./cart.html";
    });

    document.querySelector(".search").addEventListener("submit", (event) => {
      event.preventDefault();
      const query = document.querySelector(".search input").value.trim();
      window.location.href = `../index.html?search=${encodeURIComponent(query)}`;
    });
    document.querySelector(".category-nav").addEventListener("click", (event) => {
      const link = event.target.closest("[data-nav-category]");
      if (!link || link.dataset.navCategory === "My Orders") return;
      event.preventDefault();
      window.location.href = `../index.html?category=${encodeURIComponent(link.dataset.navCategory)}`;
    });

    const relatedProducts = all
      .filter((item) => item.id !== product.id && item.category === product.category)
      .concat(all.filter((item) => item.id !== product.id && item.isPopular && item.category !== product.category))
      .slice(0, 8);
    document.getElementById("related-product-track").innerHTML = relatedProducts.map((item) => `
      <a class="related-product-card" href="./product.html?id=${encodeURIComponent(item.id)}">
        <img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.name)}" loading="lazy" data-hide-on-error>
        <span class="eyebrow">${escapeHtml(item.category)}</span>
        <strong>${escapeHtml(item.name)}</strong>
        <span class="related-product-price">₹${Number(item.price).toLocaleString("en-IN")}</span>
      </a>
    `).join("");

    const relatedTrack = document.getElementById("related-product-track");
    document.querySelector("[data-related-previous]").addEventListener("click", () => {
      relatedTrack.scrollBy({ left: -relatedTrack.clientWidth * .8, behavior: "smooth" });
    });
    document.querySelector("[data-related-next]").addEventListener("click", () => {
      relatedTrack.scrollBy({ left: relatedTrack.clientWidth * .8, behavior: "smooth" });
    });
  }

  async function init() {
    let product;
    try {
      product = await trayCatalog.get(productId);
    } catch (error) {
      if (error.status === 404) {
        window.location.replace("../index.html");
        return;
      }
      document.getElementById("product-name").textContent = "We couldn’t load this dish";
      trayNotify("Check your connection and try again.");
      return;
    }

    // Related dishes are optional. The page still works if the list can't be loaded.
    let all = [];
    try { all = await trayCatalog.list(); } catch (_) {}
    renderProduct(product, all);
  }

  init();
})();
