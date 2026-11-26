"""Static checks on the frontend: no inline script or inline event handlers, and the
Vercel header matches the policy the backend builds."""

import json
import re
from pathlib import Path

from app.security.csp import build_frontend_policy

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"

INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.IGNORECASE)
HTML_EVENT_ATTRIBUTE = re.compile(r"<[^>]+\s on[a-z]+\s*=", re.IGNORECASE)
# Also catches handlers written inside JavaScript template strings, such as onerror=\"...\".
SCRIPT_EVENT_ATTRIBUTE = re.compile(r"(?<![\w.])on(?:error|load|click|submit|change|focus|blur)\s*=\s*\\?[\"']")


def _files(suffix):
    return sorted(path for path in FRONTEND.rglob(f"*{suffix}") if "node_modules" not in path.parts)


def test_html_pages_have_no_inline_script():
    offenders = [str(p.relative_to(FRONTEND)) for p in _files(".html")
                 if INLINE_SCRIPT.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_no_inline_event_handler_attributes_in_html_or_js():
    offenders = []
    for path in _files(".html"):
        if HTML_EVENT_ATTRIBUTE.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(FRONTEND)))
    for path in _files(".js"):
        if SCRIPT_EVENT_ATTRIBUTE.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(FRONTEND)))
    assert offenders == []


def test_vercel_content_security_policy_matches_backend_policy():
    config = json.loads((FRONTEND / "vercel.json").read_text(encoding="utf-8"))
    headers = {h["key"]: h["value"] for block in config["headers"] for h in block["headers"]}
    assert headers["Content-Security-Policy"] == build_frontend_policy(
        ["images.unsplash.com"], upgrade_insecure=True
    )
