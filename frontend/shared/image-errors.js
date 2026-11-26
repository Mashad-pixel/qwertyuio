(function () {
  // Hides any image marked data-hide-on-error when it fails to load. Image errors don't bubble,
  // so this listens during the capture phase. Inline onerror handlers are blocked by the CSP.
  document.addEventListener("error", (event) => {
    const image = event.target;
    if (image instanceof HTMLImageElement && image.hasAttribute("data-hide-on-error")) {
      image.style.display = "none";
    }
  }, true);
})();
