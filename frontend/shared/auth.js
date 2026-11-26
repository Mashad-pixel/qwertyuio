(function () {
  window.trayAuth = {
    async login(email, password) {
      return trayApi.post("/auth/login", { email, password });
    },
    async currentUser() {
      return trayApi.get("/auth/me");
    },
    async logout() {
      return trayApi.post("/auth/logout", {});
    }
  };
})();
