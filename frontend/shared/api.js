(function () {
  const baseUrl = window.TRAYUP_CONFIG?.apiBaseUrl || "/api";
  const unsafeMethods = new Set(["POST", "PATCH", "PUT", "DELETE"]);
  let csrfTokenPromise = null;

  // The CSRF token is tied to the server session, so it is fetched once and reused until
  // the server rejects it (after login/logout, or when it expires).
  function getCsrfToken() {
    if (!csrfTokenPromise) {
      csrfTokenPromise = fetch(`${baseUrl}/csrf-token`, {
        credentials: "include",
        headers: { "Accept": "application/json" }
      })
        .then(async (response) => {
          const data = await response.json().catch(() => null);
          if (!response.ok || !data?.csrf_token) throw new Error("Could not load the security token. Please retry.");
          return data.csrf_token;
        })
        .catch((error) => {
          csrfTokenPromise = null;
          throw error;
        });
    }
    return csrfTokenPromise;
  }

  async function send(method, path, body, extraHeaders) {
    const headers = { "Accept": "application/json", ...(extraHeaders || {}) };
    const options = { method, credentials: "include", headers };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    if (unsafeMethods.has(method)) {
      headers["X-CSRFToken"] = await getCsrfToken();
    }
    const response = await fetch(`${baseUrl}${path}`, options);
    let data = null;
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) {
      const error = new Error(data?.message || "Request failed");
      error.status = response.status;
      error.code = data?.error?.code;
      error.data = data;
      throw error;
    }
    return data;
  }

  async function request(method, path, body, options) {
    const extraHeaders = options?.headers;
    try {
      return await send(method, path, body, extraHeaders);
    } catch (error) {
      // A CSRF rejection happens before the view runs, so retrying once with a fresh token is safe.
      if (unsafeMethods.has(method) && error.code === "CSRF_TOKEN_INVALID") {
        csrfTokenPromise = null;
        return send(method, path, body, extraHeaders);
      }
      throw error;
    }
  }

  window.trayApi = {
    get: (path) => request("GET", path),
    post: (path, body, options) => request("POST", path, body, options),
    patch: (path, body, options) => request("PATCH", path, body, options),
    put: (path, body, options) => request("PUT", path, body, options),
    del: (path, options) => request("DELETE", path, undefined, options)
  };
})();
