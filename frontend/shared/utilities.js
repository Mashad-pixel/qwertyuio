(function () {
  window.trayUtils = {
    escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;"
      })[character]);
    },
    rupees(value) {
      return `₹${Number(value).toLocaleString("en-IN")}`;
    }
  };
})();
