(function () {
  window.trayValidation = {
    required(value) {
      return typeof value === "string" && value.trim().length > 0;
    },
    email(value) {
      return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
    },
    phone(value) {
      const normalized = String(value ?? "").replace(/[\s-]/g, "");
      return /^(?:\+91)?[6-9]\d{9}$/.test(normalized);
    }
  };
})();
