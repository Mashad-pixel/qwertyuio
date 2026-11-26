"""Content-Security-Policy builders.

Pages are served without inline script: every script is a same-origin file, a pinned
third-party host, or Razorpay's checkout. Inline <style> and style attributes are
still used by the frontend, so style-src allows 'unsafe-inline'. That is a much
smaller risk than allowing inline script, which is what CSP is mainly there to stop.

Image sources are built from the same allowlist that governs menu image URLs, so the
two rules cannot drift apart.
"""

from app.security.url_rules import normalize_allowed_hosts

RAZORPAY_ORIGINS = ["https://*.razorpay.com"]
SCRIPT_HOSTS = ["https://cdnjs.cloudflare.com"]
STYLE_HOSTS = ["https://fonts.googleapis.com"]
FONT_HOSTS = ["https://fonts.gstatic.com"]

API_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def _render(directives):
    parts = []
    for name, sources in directives:
        parts.append(" ".join([name, *sources]) if sources else name)
    return "; ".join(parts)


def build_frontend_policy(image_hosts, upgrade_insecure=False):
    image_sources = ["'self'", "data:"] + [f"https://{host}" for host in sorted(normalize_allowed_hosts(image_hosts))]
    directives = [
        ("default-src", ["'self'"]),
        ("script-src", ["'self'", *SCRIPT_HOSTS, *RAZORPAY_ORIGINS]),
        ("style-src", ["'self'", "'unsafe-inline'", *STYLE_HOSTS]),
        ("img-src", image_sources),
        ("font-src", ["'self'", "data:", *FONT_HOSTS]),
        ("connect-src", ["'self'", *RAZORPAY_ORIGINS]),
        ("frame-src", RAZORPAY_ORIGINS),
        ("frame-ancestors", ["'none'"]),
        ("base-uri", ["'self'"]),
        ("form-action", ["'self'"]),
        ("object-src", ["'none'"]),
    ]
    if upgrade_insecure:
        directives.append(("upgrade-insecure-requests", []))
    return _render(directives)


def build_api_policy():
    return API_POLICY
