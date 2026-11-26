(function () {
  const componentScript = Array.from(document.scripts).find((script) =>
    (script.getAttribute("src") || "").includes("shared/components.js")
  );
  const frontendBase = componentScript
    ? new URL("../", new URL(componentScript.getAttribute("src"), document.baseURI))
    : new URL("../", document.baseURI);

  function siteUrl(path) {
    return new URL(path, frontendBase).href;
  }

  window.trayComponents = {
    header(active = "") {
      const wrapSearchField = document.body.classList.contains("home-page");
      const loginNext = window.location.pathname.endsWith("/student/checkout.html") ? "?next=checkout.html" : "";
      return `
        <header class="top-strip">
          <div class="container nav-main">
            <a class="brand" href="${siteUrl("index.html")}" aria-label="TrayUP home">
              <span>TrayUP</span>
            </a>
            <form class="search" role="search">
              ${wrapSearchField ? '<div class="search-field">' : ""}
                <span class="search-sticker search-sticker-fork" aria-hidden="true">
                  <svg viewBox="0 0 48 48"><path d="M15 5v12c0 4 3 7 7 7v19M23 24V5M31 5v12c0 4-3 7-7 7M15 17H31" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </span>
                <span class="search-sticker search-sticker-spoon" aria-hidden="true">
                  <svg viewBox="0 0 48 48"><ellipse cx="31" cy="13" rx="9" ry="12" fill="currentColor"/><path d="M28 23L17 43" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round"/></svg>
                </span>
                <span class="search-sticker search-sticker-burger" aria-hidden="true">
                  <svg viewBox="0 0 48 48"><path d="M7 20c1-8 7-13 17-13s16 5 17 13H7zm0 6h34v6H7zm3 12h28l-3-7H13l-3 7z" fill="currentColor"/><circle cx="17" cy="14" r="1.5" fill="#fff"/><circle cx="25" cy="12" r="1.5" fill="#fff"/><circle cx="32" cy="15" r="1.5" fill="#fff"/></svg>
                </span>
                <span class="search-sticker search-sticker-chef" aria-hidden="true">
                  <svg viewBox="0 0 48 48"><path d="M10 22c-5-1-7-7-3-11 3-3 7-2 10 0 1-6 10-7 13-2 5-2 11 2 10 8 4 1 6 5 4 9-2 5-7 6-12 4H16c-5 1-9-3-6-8zM13 31h25l-2 11H15l-2-11z" fill="currentColor"/><path d="M33 33l1.5 4L39 38l-3.5 3L36 45l-4-2-4 2 1-4-3-3 4-1z" fill="#fff"/></svg>
                </span>
                <span class="search-icon" aria-hidden="true"></span>
                <span class="search-placeholder" aria-hidden="true">
                  Search <span class="bitten-word">for a bite</span>...
                </span>
                <input type="search" placeholder="" aria-label="Search menu" autocomplete="off" aria-controls="menu-suggestions">
              ${wrapSearchField ? "</div>" : ""}
              <div class="search-suggestions" id="menu-suggestions" role="listbox" aria-label="Menu suggestions" hidden></div>
              <button type="submit" aria-label="Search"></button>
            </form>
            <nav class="nav-actions" aria-label="Account navigation">
              <a class="sign-link" href="${siteUrl("student/cart.html")}" aria-label="View cart">CART</a>
              <button class="cart-btn" id="open-cart" type="button" aria-label="Open cart">🛒
                <span class="cart-count" id="cart-count">0</span>
              </button>
              <a class="login-link" href="${siteUrl("loginpage.html")}${loginNext}" aria-label="Log in to your TrayUP account">
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <circle cx="12" cy="8" r="3.25"></circle>
                  <path d="M5.5 19a6.5 6.5 0 0 1 13 0"></path>
                </svg>
                <span>Log in</span>
              </a>
            </nav>
          </div>
          <nav class="category-nav" aria-label="Main navigation">
            ${["All","Breakfast","Lunch","Snacks","Drinks","Popular","My Orders"].map((item) =>
              `<a class="${active === item ? "active" : ""}" data-nav-category="${item}" href="${item === "My Orders" ? siteUrl("student/tracking.html") : siteUrl("index.html")}">${item}</a>`
            ).join("")}
          </nav>
        </header>`;
    }
  };
})();
