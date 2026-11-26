(function () {
  const categories = ["All", "Breakfast", "Lunch", "Snacks", "Drinks", "Popular"];

  const header = document.getElementById("app-header");
  const grid = document.getElementById("food-grid");
  const drawer = document.getElementById("cart-drawer");
  const popularPeriods = document.getElementById("popular-periods");
  const heroTrack = document.getElementById("hero-track");
  const heroCount = document.getElementById("hero-slide-count");
  const heroCarousel = document.querySelector(".menu-hero");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const heroTransitionDuration = 700;
  let activeCategory = "Popular";
  let activePeriod = "day";
  let activeMood = "";
  let heroProducts = [];
  let heroIndex = 0;
  let heroTimer = null;
  let heroTransitionTimer = null;
  let queuedHeroDirections = [];
  let heroPaused = reducedMotion.matches;
  let heroTransitioning = false;
  let heroDirection = 1;
  let catalog = [];
  let popularityByPeriod = { day: new Map(), week: new Map(), month: new Map() };
  let loaded = false;
  const searchParams = new URLSearchParams(window.location.search);
  const requestedCategory = searchParams.get("category");
  if (categories.includes(requestedCategory)) activeCategory = requestedCategory;
  const initialSearch = searchParams.get("search");
  if (initialSearch) activeCategory = "All";
  header.innerHTML = trayComponents.header(activeCategory);
  const searchInput = document.querySelector(".search input");
  if (initialSearch) searchInput.value = initialSearch;

  function rupees(value) {
    return `₹${Number(value).toLocaleString("en-IN")}`;
  }

  function normalizeSearch(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  }

  function searchScore(item, rawQuery) {
    const query = normalizeSearch(rawQuery);
    if (!query) return 1;

    const name = normalizeSearch(item.name);
    const category = normalizeSearch(item.category);
    const description = normalizeSearch(item.description);
    const searchable = `${name} ${category} ${description}`;
    const queryWords = query.split(" ").filter(Boolean);

    if (name === query) return 100;
    if (name.startsWith(query)) return 90;
    if (name.includes(query)) return 80;
    if (category === query) return 70;
    if (category.includes(query)) return 60;

    let score = 0;
    queryWords.forEach((word) => {
      if (word.length < 2) return;
      if (name.includes(word)) score += 35;
      else if (category.includes(word)) score += 25;
      else if (description.includes(word)) score += 15;
      else if (searchable.includes(word)) score += 5;
    });

    return score;
  }

  function getPopularCounts(period) {
    return popularityByPeriod[period] || new Map();
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;"
    })[character]);
  }

  function isEgg(item) {
    return /\begg\b/i.test(`${item.name} ${item.description}`);
  }

  // Diet is shown only when the canteen has recorded it. Unknown is not treated as vegetarian.
  function dietClass(item) {
    if (isEgg(item)) return "is-egg";
    if (!item.hasDiet) return "is-unknown";
    return item.isVeg ? "is-veg" : "is-non-veg";
  }

  function dietTitle(item) {
    if (isEgg(item)) return "Contains egg";
    if (!item.hasDiet) return "Diet not recorded";
    return item.isVeg ? "Vegetarian" : "Non-vegetarian";
  }

  function matchesMood(item, mood) {
    const text = `${item.name} ${item.description}`.toLowerCase();
    const matches = {
      spicy: /\b(masala|biryani|chole|pav bhaji|pakoda|momos|chilli|spicy)\b/,
      comfort: /\b(dosa|idli|pongal|paratha|thali|dal|rajma|rice|poori)\b/,
      quick: /\b(samosa|fries|burger|momos|sandwich|pakoda|pizza|puri)\b/,
      sweet: /\b(chocolate|oreo|mango|milkshake|lassi|strawberry|sweet)\b/,
      refreshing: /\b(juice|soda|lime|lassi|buttermilk|water|cold coffee|milkshake)\b/
    };
    return Boolean(matches[mood] && matches[mood].test(text));
  }

  function renderCategoryRail() {
    const rail = document.getElementById("category-rail");
    const categoryItems = [];
    Array.from(new Set(catalog.map((item) => item.category))).forEach((category) => {
      const item = catalog.find((product) => product.category === category && product.isAvailable);
      if (item) categoryItems.push({ category, item });
    });
    rail.innerHTML = categoryItems.map(({ category, item }, index) => `
      <button class="category-tile" type="button" data-category="${escapeHtml(category)}" aria-label="Browse ${escapeHtml(category)}">
        <img src="${escapeHtml(item.image)}" alt="" loading="lazy">
        <span class="category-number">0${index + 1}</span>
        <strong>${escapeHtml(category)}</strong>
        <span class="category-arrow" aria-hidden="true">↗</span>
      </button>
    `).join("");
  }

  function heroSlideMarkup(item) {
    return `
      <a class="hero-slide" href="./student/product.html?id=${encodeURIComponent(item.id)}"
        aria-label="Order ${escapeHtml(item.name)} for ${rupees(item.price)}. ${escapeHtml(item.description)}"
        aria-hidden="true" tabindex="-1" inert>
        <img class="hero-slide-image" src="${escapeHtml(item.image)}" alt="" loading="eager">
        <div class="hero-copy">
          <div class="open-status">Made for the in-between</div>
          <span class="hero-category">${escapeHtml(item.category)} · Popular pick</span>
          <h1>${escapeHtml(item.name)}</h1>
          <p>${escapeHtml(item.description)}</p>
          <div class="hero-slide-footer">
            <span class="hero-slide-price">${rupees(item.price)}</span>
            <span class="hero-slide-cta">View dish &amp; order <span aria-hidden="true">→</span></span>
          </div>
        </div>
      </a>
    `;
  }

  function renderHero() {
    const counts = getPopularCounts("day");
    heroProducts = catalog
      .filter((item) => item.isPopular && item.isAvailable)
      .map((item) => ({ item, count: counts.get(item.id) || 0 }))
      .sort((a, b) => b.count - a.count || a.item.name.localeCompare(b.item.name))
      .map(({ item }) => item);

    if (!heroProducts.length) {
      heroCarousel.hidden = true;
      return;
    }

    heroCarousel.hidden = false;
    heroIndex = 0;
    heroTrack.innerHTML = heroSlideMarkup(heroProducts[heroIndex]);
    heroTrack.style.transition = "none";
    heroTrack.style.transform = "translateX(0)";
    setAccessibleHeroSlide(0);
    heroCount.textContent = `01 / ${String(heroProducts.length).padStart(2, "0")}`;
    heroTrack.getBoundingClientRect();
    heroTrack.style.transition = "";
    updateHeroAutoplay();
  }

  function setAccessibleHeroSlide(activeIndex) {
    Array.from(heroTrack.children).forEach((slide, index) => {
      const active = index === activeIndex;
      slide.setAttribute("aria-hidden", String(!active));
      slide.tabIndex = active ? 0 : -1;
      if (active) slide.removeAttribute("inert");
      else slide.setAttribute("inert", "");
    });
  }

  function finishHeroTransition() {
    if (!heroTransitioning) return;
    window.clearTimeout(heroTransitionTimer);
    heroTransitionTimer = null;
    if (heroDirection > 0) heroTrack.firstElementChild.remove();
    else heroTrack.lastElementChild.remove();
    heroTrack.style.transition = "none";
    heroTrack.style.transform = "translateX(0)";
    setAccessibleHeroSlide(0);
    heroTransitioning = false;
    heroTrack.getBoundingClientRect();
    heroTrack.style.transition = "";

    const queuedDirection = queuedHeroDirections.shift();
    if (queuedDirection) showHeroSlide(queuedDirection, true);
  }

  function showHeroSlide(direction, queueIfTransitioning = false) {
    if (heroProducts.length < 2) return;
    if (heroTransitioning) {
      if (queueIfTransitioning && queuedHeroDirections.length < 8) {
        queuedHeroDirections.push(direction);
      }
      return;
    }

    heroDirection = direction;
    heroIndex = (heroIndex + direction + heroProducts.length) % heroProducts.length;
    const nextSlide = heroSlideMarkup(heroProducts[heroIndex]);
    if (direction > 0) {
      heroTrack.insertAdjacentHTML("beforeend", nextSlide);
      heroTrack.style.transform = "translateX(0)";
      heroTrack.getBoundingClientRect();
      heroTrack.style.transform = "translateX(-100%)";
      setAccessibleHeroSlide(1);
    } else {
      heroTrack.insertAdjacentHTML("afterbegin", nextSlide);
      heroTrack.style.transition = "none";
      heroTrack.style.transform = "translateX(-100%)";
      heroTrack.getBoundingClientRect();
      setAccessibleHeroSlide(0);
      heroTrack.style.transition = "";
      heroTrack.style.transform = "translateX(0)";
    }
    heroTransitioning = true;
    heroCount.textContent = `${String(heroIndex + 1).padStart(2, "0")} / ${String(heroProducts.length).padStart(2, "0")}`;
    heroTransitionTimer = window.setTimeout(finishHeroTransition, heroTransitionDuration + 300);
    if (reducedMotion.matches) finishHeroTransition();
  }

  ["transitionend", "transitioncancel"].forEach((eventName) => {
    heroTrack.addEventListener(eventName, (event) => {
      if (event.target === heroTrack && event.propertyName === "transform") finishHeroTransition();
    });
  });

  function updateHeroAutoplay() {
    window.clearInterval(heroTimer);
    if (heroPaused || heroProducts.length < 2 || document.hidden) return;
    heroTimer = window.setInterval(() => showHeroSlide(1), 5200);
  }

  document.getElementById("hero-previous").addEventListener("click", () => showHeroSlide(-1, true));
  document.getElementById("hero-next").addEventListener("click", () => showHeroSlide(1, true));
  heroCarousel.addEventListener("mouseenter", () => window.clearInterval(heroTimer));
  heroCarousel.addEventListener("mouseleave", updateHeroAutoplay);
  heroCarousel.addEventListener("focusin", () => window.clearInterval(heroTimer));
  heroCarousel.addEventListener("focusout", (event) => {
    if (!heroCarousel.contains(event.relatedTarget)) updateHeroAutoplay();
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && heroTransitioning) finishHeroTransition();
    updateHeroAutoplay();
  });
  reducedMotion.addEventListener?.("change", (event) => {
    heroPaused = event.matches;
    if (heroPaused && heroTransitioning) finishHeroTransition();
    updateHeroAutoplay();
  });

  popularPeriods.addEventListener("click", (event) => {
    const button = event.target.closest("[data-period]");
    if (!button) return;
    activePeriod = button.dataset.period;
    popularPeriods.querySelectorAll("button").forEach((entry) => entry.classList.toggle("active", entry === button));
    renderCatalog();
  });

  function renderCatalog() {
    if (!loaded) return;
    const query = document.querySelector(".search input")?.value.trim() || "";
    const normalizedQuery = normalizeSearch(query);
    const availability = document.getElementById("availability-filter")?.value || "all";
    const diet = document.getElementById("diet-filter")?.value || "all";
    const isPopularView = activeCategory === "Popular";
    const popularCounts = isPopularView ? getPopularCounts(activePeriod) : new Map();
    popularPeriods.hidden = !isPopularView;
    let visible = catalog
      .map((item) => ({ item, score: searchScore(item, query), sales: popularCounts.get(item.id) || 0 }))
      .filter(({ item, score }) =>
        score > 0 &&
        (!activeMood || matchesMood(item, activeMood)) &&
        (normalizedQuery ||
          activeCategory === "All" ||
          (isPopularView ? popularCounts.has(item.id) : item.category === activeCategory)) &&
        (availability !== "available" || item.isAvailable) &&
        (diet === "all" ||
          (diet === "veg" && item.isVeg) ||
          (diet === "nonveg" && item.hasDiet && !item.isVeg && !isEgg(item)) ||
          (diet === "egg" && isEgg(item)))
      )
      .sort((a, b) => isPopularView ? b.sales - a.sales || b.score - a.score : b.score - a.score)
      .map(({ item, sales }, index) => ({ ...item, periodOrders: sales, popularityRank: isPopularView ? index + 1 : 0 }));

    if (!visible.length) {
      grid.innerHTML = "";
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.style.gridColumn = "1/-1";
      const title = document.createElement("h3");
      title.textContent = normalizedQuery ? "Couldn't find that craving" :
        isPopularView ? "No orders recorded for this period yet" : "No dishes found";
      const copy = document.createElement("p");
      copy.textContent = normalizedQuery ? `No menu items matched "${query}". Try another dish or category.` :
        isPopularView ? "Dishes appear here once they are ordered in this period. Choose All to browse the full menu." : "Try a different category or search.";
      empty.append(title, copy);
      grid.appendChild(empty);
      const heading = document.querySelector(".menu-heading h2");
      heading.textContent = normalizedQuery ? "Search results" : isPopularView ? "Popular today" : activeCategory;
      return;
    }
    const heading = document.querySelector(".menu-heading h2");
    popularPeriods.hidden = !isPopularView;
    heading.textContent = normalizedQuery ? `Results for "${query}"` :
      activeCategory === "Popular" ? `Popular ${activePeriod === "day" ? "today" : activePeriod === "week" ? "this week" : "this month"}` :
      activeCategory === "All" ? "All dishes" : activeCategory;
    grid.innerHTML = visible.map((item) => `
      <article class="food-card" data-id="${escapeHtml(item.id)}" tabindex="0" role="link" aria-label="View ${escapeHtml(item.name)} details">
        <div class="food-card-image-wrap">
          <img class="food-card-image" src="${escapeHtml(item.image)}" alt="${escapeHtml(item.name)}" loading="lazy" data-fallback-name="${escapeHtml(item.name)}">
          ${item.isPopular ? '<span class="food-card-ribbon">Campus pick</span>' : ""}
        </div>
        <div class="food-card-body">
          <span class="eyebrow">${escapeHtml(item.category)}${item.popularityRank ? ` · #${item.popularityRank} popular` : ""}</span>
          <h3>${escapeHtml(item.name)}</h3>
          <p class="food-card-description">${escapeHtml(item.description || "")}</p>
          <div class="food-card-status-row">
            <span class="status ${item.isAvailable ? "" : "danger"}">${item.isAvailable ? "Available" : "Sold out"}</span>
            <span class="food-card-diet ${dietClass(item)}" title="${dietTitle(item)}">●</span>
          </div>
          ${item.popularityRank ? `<p class="food-card-orders">${item.periodOrders} ordered ${activePeriod === "day" ? "today" : activePeriod === "week" ? "this week" : "this month"}</p>` : ""}
          <div class="food-meta">
            <span class="price">${rupees(item.price)}</span>
            <div class="food-card-actions" data-card-actions="${escapeHtml(item.id)}">
              <button class="food-card-add" type="button" data-card-add="${escapeHtml(item.id)}" ${item.isAvailable ? "" : "disabled"}>Add <span aria-hidden="true">+</span></button>
              <div class="food-card-quantity" data-card-quantity-control="${escapeHtml(item.id)}" hidden>
                <button type="button" data-card-qty="-1" data-id="${escapeHtml(item.id)}" aria-label="Remove one ${escapeHtml(item.name)}">−</button>
                <span data-card-quantity>0</span>
                <button type="button" data-card-qty="1" data-id="${escapeHtml(item.id)}" aria-label="Add one ${escapeHtml(item.name)}">+</button>
              </div>
            </div>
          </div>
        </div>
      </article>
    `).join("");
    updateCardQuantities();
  }

  function getCart() {
    return trayStorage.getCart();
  }

  function saveCart(cart) {
    trayStorage.set("trayup-cart", cart);
    renderCart();
  }

  function renderCart() {
    const cart = getCart();
    const quantity = cart.reduce((sum, item) => sum + item.qty, 0);
    document.getElementById("cart-count").textContent = quantity;
    document.getElementById("mobile-cart-count").textContent = quantity;
    document.getElementById("cart-total").textContent = rupees(cart.reduce((sum, item) => sum + item.price * item.qty, 0));
    document.getElementById("cart-items").innerHTML = cart.length ? cart.map((item) => `
      <div class="cart-item">
        <img src="${escapeHtml(item.image)}" alt="">
        <div><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(rupees(item.price))}</span>
          <div class="qty-control">
            <button type="button" data-qty="-1" data-id="${escapeHtml(item.id)}" aria-label="Decrease quantity">−</button>
            <span>${escapeHtml(item.qty)}</span>
            <button type="button" data-qty="1" data-id="${escapeHtml(item.id)}" aria-label="Increase quantity">+</button>
          </div>
        </div>
      </div>
    `).join("") : `<div class="empty-state"><p>Your cart is empty</p></div>`;
    updateCardQuantities();
    const count = document.getElementById("cart-count");
    count.classList.remove("cart-count-pop");
    requestAnimationFrame(() => count.classList.add("cart-count-pop"));
  }

  function updateCardQuantities() {
    const cart = getCart();
    document.querySelectorAll("[data-card-actions]").forEach((actions) => {
      const item = cart.find((entry) => entry.id === Number(actions.dataset.cardActions));
      const quantity = item ? item.qty : 0;
      const addButton = actions.querySelector("[data-card-add]");
      const controls = actions.querySelector("[data-card-quantity-control]");
      if (!addButton || !controls) return;
      addButton.hidden = quantity > 0;
      controls.hidden = quantity <= 0;
      controls.querySelector("[data-card-quantity]").textContent = quantity;
    });
  }

  // Fallback artwork for dishes whose photo fails to load. Image errors don't bubble, so this
  // listens during the capture phase. Inline onerror handlers are not allowed by the CSP.
  function fallbackImageSrc(name) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="450"><rect width="100%" height="100%" fill="#2d322f"/><text x="50%" y="50%" text-anchor="middle" fill="#f7f4eb">${escapeHtml(name)}</text></svg>`;
    return `data:image/svg+xml,${encodeURIComponent(svg)}`;
  }
  grid.addEventListener("error", (event) => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || !image.dataset.fallbackName || image.dataset.fallbackApplied) return;
    image.dataset.fallbackApplied = "true";
    image.src = fallbackImageSrc(image.dataset.fallbackName);
  }, true);

  grid.addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-card-add]");
    const quantityButton = event.target.closest("[data-card-qty]");
    if (addButton || quantityButton) {
      event.stopPropagation();
      const id = Number((addButton || quantityButton).dataset.id || (addButton || quantityButton).dataset.cardAdd);
      const product = catalog.find((item) => item.id === id);
      if (!product || !product.isAvailable) return;
      const cart = getCart();
      const item = cart.find((entry) => entry.id === id);
      const change = quantityButton ? Number(quantityButton.dataset.cardQty) : 1;
      if (item) item.qty += change;
      else if (change > 0) cart.push({ id: product.id, name: product.name, price: product.price, image: product.image, qty: change });
      saveCart(cart.filter((entry) => entry.qty > 0));
      if (change > 0 && window.trayNotify) window.trayNotify("Good choice! Added to your tray.");
      return;
    }
    const card = event.target.closest(".food-card");
    if (card) window.location.href = `./student/product.html?id=${encodeURIComponent(card.dataset.id)}`;
  });
  grid.addEventListener("keydown", (event) => {
    const card = event.target.closest(".food-card");
    if (event.target.closest("button")) return;
    if (card && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      window.location.href = `./student/product.html?id=${encodeURIComponent(card.dataset.id)}`;
    }
  });

  document.getElementById("open-cart").addEventListener("click", () => drawer.classList.add("open"));
  document.getElementById("close-cart").addEventListener("click", () => drawer.classList.remove("open"));
  const searchForm = document.querySelector(".search");
  const suggestionList = document.getElementById("menu-suggestions");

  function renderSuggestions(query) {
    const trimmed = query.trim();
    if (!trimmed) {
      suggestionList.hidden = true;
      suggestionList.innerHTML = "";
      return;
    }
    const matches = catalog
      .map((item) => ({ item, score: searchScore(item, trimmed) }))
      .filter(({ score }) => score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 5);
    suggestionList.hidden = false;
    suggestionList.innerHTML = matches.length
      ? matches.map(({ item }) => `
        <button class="search-suggestion" type="button" role="option" data-suggestion-id="${escapeHtml(item.id)}">
          <img src="${escapeHtml(item.image)}" alt="" loading="lazy">
          <span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.category)}</small></span>
          <b>${rupees(item.price)}</b>
        </button>`).join("")
      : '<p class="search-no-results">Couldn’t find that craving. Try another dish.</p>';
  }

  function selectSuggestion(button) {
    if (!button) return;
    window.location.href = `./student/product.html?id=${encodeURIComponent(button.dataset.suggestionId)}`;
  }

  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    suggestionList.hidden = true;
    activeCategory = "All";
    document.querySelectorAll(".category-nav a").forEach((entry) =>
      entry.classList.toggle("active", entry.dataset.navCategory === "All")
    );
    renderCatalog();
    document.getElementById("popular").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  searchInput.addEventListener("input", () => {
    renderSuggestions(searchInput.value);
    if (searchInput.value.trim()) {
      activeCategory = "All";
      document.querySelectorAll(".category-nav a").forEach((entry) =>
        entry.classList.toggle("active", entry.dataset.navCategory === "All")
      );
    }
    renderCatalog();
  });
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" && !suggestionList.hidden) {
      const firstSuggestion = suggestionList.querySelector("[data-suggestion-id]");
      if (firstSuggestion) {
        event.preventDefault();
        firstSuggestion.focus();
      }
    } else if (event.key === "Escape") {
      suggestionList.hidden = true;
    }
  });
  suggestionList.addEventListener("click", (event) => {
    selectSuggestion(event.target.closest("[data-suggestion-id]"));
  });
  suggestionList.addEventListener("keydown", (event) => {
    const buttons = Array.from(suggestionList.querySelectorAll("[data-suggestion-id]"));
    const currentIndex = buttons.indexOf(document.activeElement);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const direction = event.key === "ArrowDown" ? 1 : -1;
      const nextIndex = (currentIndex + direction + buttons.length) % buttons.length;
      if (buttons[nextIndex]) buttons[nextIndex].focus();
    } else if (event.key === "Escape") {
      suggestionList.hidden = true;
      searchInput.focus();
    } else if (event.key === "Enter") {
      event.preventDefault();
      selectSuggestion(buttons[currentIndex]);
    }
  });
  document.addEventListener("click", (event) => {
    if (!searchForm.contains(event.target)) suggestionList.hidden = true;
  });
  document.getElementById("availability-filter").addEventListener("change", renderCatalog);
  document.getElementById("diet-filter").addEventListener("change", (event) => {
    if (event.target.value !== "all") {
      activeCategory = "All";
      document.querySelectorAll(".category-nav a").forEach((entry) =>
        entry.classList.toggle("active", entry.dataset.navCategory === "All")
      );
    }
    renderCatalog();
  });
  document.getElementById("clear-search").addEventListener("click", () => {
    document.querySelector(".search input").value = "";
    suggestionList.hidden = true;
    document.getElementById("availability-filter").value = "all";
    document.getElementById("diet-filter").value = "all";
    activeMood = "";
    document.getElementById("clear-mood").hidden = true;
    document.querySelectorAll("[data-mood]").forEach((button) => button.classList.remove("active"));
    activeCategory = "Popular";
    document.querySelectorAll(".category-nav a").forEach((entry) =>
      entry.classList.toggle("active", entry.dataset.navCategory === "Popular")
    );
    renderCatalog();
  });

  document.querySelector(".category-nav").addEventListener("click", (event) => {
    const link = event.target.closest("[data-nav-category]");
    if (!link) return;
    const category = link.dataset.navCategory;
    if (category === "My Orders") return;
    event.preventDefault();
    activeCategory = category;
    activeMood = "";
    document.getElementById("clear-mood").hidden = true;
    document.querySelectorAll("[data-mood]").forEach((button) => button.classList.remove("active"));
    document.querySelector(".search input").value = "";
    document.querySelectorAll(".category-nav a").forEach((entry) => entry.classList.toggle("active", entry === link));
    renderCatalog();
    document.getElementById("popular").scrollIntoView({ behavior: "smooth" });
  });

  document.getElementById("category-rail").addEventListener("click", (event) => {
    const tile = event.target.closest("[data-category]");
    if (!tile) return;
    activeCategory = tile.dataset.category;
    activeMood = "";
    document.getElementById("clear-mood").hidden = true;
    document.querySelectorAll("[data-mood]").forEach((button) => button.classList.remove("active"));
    searchInput.value = "";
    document.querySelectorAll(".category-nav a").forEach((link) =>
      link.classList.toggle("active", link.dataset.navCategory === activeCategory)
    );
    renderCatalog();
    document.getElementById("popular").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  document.getElementById("mood-choices").addEventListener("click", (event) => {
    const button = event.target.closest("[data-mood]");
    if (!button) return;
    activeMood = activeMood === button.dataset.mood ? "" : button.dataset.mood;
    activeCategory = "All";
    searchInput.value = "";
    document.getElementById("clear-mood").hidden = !activeMood;
    document.querySelectorAll("[data-mood]").forEach((choice) =>
      choice.classList.toggle("active", choice.dataset.mood === activeMood)
    );
    document.querySelectorAll(".category-nav a").forEach((link) =>
      link.classList.toggle("active", link.dataset.navCategory === "All")
    );
    renderCatalog();
    document.getElementById("popular").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  document.getElementById("clear-mood").addEventListener("click", () => {
    activeMood = "";
    document.querySelectorAll("[data-mood]").forEach((button) => button.classList.remove("active"));
    document.getElementById("clear-mood").hidden = true;
    renderCatalog();
  });

  document.getElementById("surprise-me").addEventListener("click", () => {
    const visibleIds = new Set(Array.from(grid.querySelectorAll(".food-card"), (card) => Number(card.dataset.id)));
    const options = catalog.filter((item) => item.isAvailable && visibleIds.has(item.id));
    const result = document.getElementById("roulette-result");
    if (!options.length) {
      result.innerHTML = '<div class="roulette-placeholder"><span>!</span></div><p>No available dishes match those filters. Clear filters and try again.</p>';
      result.classList.add("is-revealed");
      return;
    }
    const item = options[Math.floor(Math.random() * options.length)];
    result.innerHTML = `
      <a class="roulette-dish" href="./student/product.html?id=${encodeURIComponent(item.id)}">
        <img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.name)}">
        <span class="roulette-dish-info"><small>YOUR RANDOM PICK</small><strong>${escapeHtml(item.name)}</strong><b>${rupees(item.price)}</b></span>
        <span class="roulette-dish-arrow" aria-hidden="true">↗</span>
      </a>`;
    result.classList.remove("is-revealed");
    requestAnimationFrame(() => result.classList.add("is-revealed"));
  });

  document.querySelector("[data-mobile-cart]").addEventListener("click", () => drawer.classList.add("open"));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && drawer.classList.contains("open")) {
      drawer.classList.remove("open");
      document.getElementById("open-cart").focus();
    }
  });

  document.getElementById("cart-items").addEventListener("click", (event) => {
    const button = event.target.closest("[data-qty]");
    if (!button) return;
    const cart = getCart();
    const item = cart.find((entry) => entry.id === Number(button.dataset.id));
    if (!item) return;
    item.qty += Number(button.dataset.qty);
    saveCart(cart.filter((entry) => entry.qty > 0));
  });

  async function loadMenu() {
    try {
      const [items, day, week, month] = await Promise.all([
        trayCatalog.list(),
        trayCatalog.popularity("day"),
        trayCatalog.popularity("week"),
        trayCatalog.popularity("month")
      ]);
      catalog = items;
      popularityByPeriod = { day, week, month };
      // "Campus pick" marks the five most-ordered dishes this month.
      const topIds = new Set([...month.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([id]) => id));
      catalog.forEach((item) => { item.isPopular = topIds.has(item.id); });
      loaded = true;
      renderCategoryRail();
      renderHero();
      renderCatalog();
    } catch (error) {
      grid.innerHTML = '<div class="empty-state" style="grid-column:1/-1"><h3>We couldn’t load the menu</h3><p>Check your connection and refresh the page.</p></div>';
    }
  }

  renderCart();
  grid.innerHTML = '<div class="empty-state" style="grid-column:1/-1"><p>Loading the menu…</p></div>';
  loadMenu();
})();
