(function () {
  // The menu comes from the backend. Nothing here is hardcoded, and nothing is kept in local
  // storage, so the page always shows what the database holds. Responses are cached in memory
  // for the life of the page. Popularity is cached for a short time, since it changes.
  const POPULARITY_TTL_MS = 60 * 1000;
  let listPromise = null;
  const popularityCache = {};

  function mapItem(raw) {
    const hasDiet = typeof raw.is_veg === "boolean";
    return {
      id: Number(raw.id),
      name: raw.name,
      description: raw.description || "",
      category: raw.category,
      // The backend stores whole paise. The UI and cart use rupees.
      price: Number(raw.price_paise || 0) / 100,
      image: raw.image_url || "",
      hasDiet,
      isVeg: raw.is_veg === true,
      isAvailable: raw.is_available !== false,
      ingredients: Array.isArray(raw.ingredients) ? raw.ingredients : [],
      preparation: raw.preparation || "",
      recipeSteps: Array.isArray(raw.recipe_steps) ? raw.recipe_steps : []
    };
  }

  function list() {
    if (!listPromise) {
      listPromise = trayApi.get("/menu")
        .then((response) => (response.items || []).map(mapItem))
        .catch((error) => { listPromise = null; throw error; });
    }
    return listPromise;
  }

  async function get(id) {
    const response = await trayApi.get(`/menu/${Number(id)}`);
    return mapItem(response.item);
  }

  function popularity(period) {
    const cached = popularityCache[period];
    if (cached && Date.now() - cached.at < POPULARITY_TTL_MS) return cached.promise;
    const promise = trayApi.get(`/menu/popular?period=${encodeURIComponent(period)}`)
      .then((response) => new Map((response.items || []).map((entry) => [Number(entry.menu_item_id), Number(entry.quantity)])))
      .catch((error) => { delete popularityCache[period]; throw error; });
    popularityCache[period] = { at: Date.now(), promise };
    return promise;
  }

  window.trayCatalog = { list, get, popularity, mapItem };
})();
