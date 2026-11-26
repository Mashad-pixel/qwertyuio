"""Static checks that the admin panel's pages are wired to real backend routes.

Reads every API call made by the admin scripts and matches it against the Flask route table (read from
the source, so no dependencies are needed). Also checks the admin HTML: referenced files exist, no inline
script or event-handler attributes (the Content-Security-Policy forbids them), no browser storage, and no
placeholder text left from the old pages.
"""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "frontend" / "admin"
SHARED = ROOT / "frontend" / "shared"


def _blueprint_prefixes():
    """Map a blueprint variable name to its url_prefix, read from the source."""
    prefixes = {}
    for path in (ROOT / "app" / "routes").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                func = node.value.func
                if getattr(func, "id", "") == "Blueprint":
                    name = node.targets[0].id
                    prefix = ""
                    for kw in node.value.keywords:
                        if kw.arg == "url_prefix":
                            prefix = kw.value.value
                    prefixes[(path.name, name)] = prefix
    return prefixes


def _routes():
    """Return (method, full path) for every route decorator in app/routes."""
    prefixes = _blueprint_prefixes()
    routes = []
    for path in (ROOT / "app" / "routes").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for deco in func.decorator_list:
                if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                    continue
                owner = deco.func.value
                if not isinstance(owner, ast.Name):
                    continue
                prefix = prefixes.get((path.name, owner.id))
                if prefix is None or not deco.args or not isinstance(deco.args[0], ast.Constant):
                    continue
                rule = deco.args[0].value
                attr = deco.func.attr
                if attr in ("get", "post", "patch", "put", "delete"):
                    methods = [attr.upper()]
                elif attr == "route":
                    methods = ["GET"]
                    for kw in deco.keywords:
                        if kw.arg == "methods":
                            methods = [m.value for m in kw.value.elts]
                else:
                    continue
                for method in methods:
                    routes.append((method, prefix + rule))
    return routes


def _rule_pattern(full_path):
    """Turn a Flask rule like /api/admin/menu/<int:item_id> into a regex."""
    escaped = re.escape(full_path)
    escaped = re.sub(r"<(?:int:)?\w+>", r"\\d+", escaped)
    return re.compile("^" + escaped + "$")


ROUTES = _routes()
ROUTE_PATTERNS = [(method, _rule_pattern(path)) for method, path in ROUTES]

API_CALL = re.compile(r"trayApi\.(get|post|patch|del|put)\(\s*([\"'`])(.*?)\2", re.S)
METHOD_FOR = {"get": "GET", "post": "POST", "patch": "PATCH", "del": "DELETE", "put": "PUT"}


def _path_for_call(raw, text, end):
    """Rebuild the request path for `trayApi.x("/a/" + id + "/suffix", ...)`.

    Each `+ expression` in the path becomes a sample id, and a string literal that follows it is part
    of the path. Text after the first `,` or `)` belongs to the body or the call's arguments, so it is
    ignored.
    """
    remainder = text[end:end + 300]
    cuts = [i for i in (remainder.find(","), remainder.find(")")) if i >= 0]
    remainder = remainder[: min(cuts)] if cuts else remainder
    if "+" not in remainder:
        return raw
    path = raw
    for piece in remainder.split("+")[1:]:
        path += "1"
        literal = re.search(r"([\"'])(.*?)\1", piece)
        if literal and literal.group(2).startswith("/"):
            path += literal.group(2)
    return path


def _normalize(path):
    path = re.sub(r"\$\{[^}]*\}", "1", path)  # template expressions become a sample integer id
    path = path.split("?", 1)[0]
    return "/api" + path


class AdminApiContractTests(unittest.TestCase):
    def test_every_admin_api_call_has_a_matching_route(self):
        problems = []
        for script in sorted(ADMIN.rglob("*.js")):
            text = script.read_text(encoding="utf-8")
            for match in API_CALL.finditer(text):
                verb, _, raw = match.groups()
                if not raw.startswith("/"):
                    continue
                method = METHOD_FOR[verb]
                path = _normalize(_path_for_call(raw, text, match.end()))
                if not any(m == method and pattern.match(path) for m, pattern in ROUTE_PATTERNS):
                    problems.append(f"{script.relative_to(ROOT)}: {method} {path}")
        self.assertEqual(problems, [], "admin scripts call routes the backend does not define")

    def test_the_admin_pages_use_the_new_account_and_category_routes(self):
        text = "\n".join(p.read_text(encoding="utf-8") for p in (ADMIN / "js").glob("*.js"))
        for needle in ["/account", "/account/password", "/account/email", "/account/sessions",
                       "/admin/categories", "/admin/canteen/settings", "/admin/canteen/status"]:
            self.assertIn(needle, text)


class AdminHtmlTests(unittest.TestCase):
    PAGES = ["login.html", "dashboard.html", "orders.html", "menu.html", "categories.html",
             "reports.html", "refunds.html", "staff.html", "settings.html"]

    def test_referenced_files_exist(self):
        for page in self.PAGES:
            html = (ADMIN / page).read_text(encoding="utf-8")
            for ref in re.findall(r'(?:src|href)="([^"#]+)"', html):
                if ref.startswith(("http", "mailto", "data:")):
                    continue
                self.assertTrue((ADMIN / ref).resolve().exists(), f"{page} references missing {ref}")

    def test_no_inline_script_or_event_handler_attributes(self):
        for page in self.PAGES:
            html = (ADMIN / page).read_text(encoding="utf-8")
            self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)", f"{page} has an inline script")
            self.assertNotRegex(html, r"\son[a-z]+\s*=", f"{page} has an inline event handler")

    def test_every_admin_page_loads_the_shared_shell_and_its_script(self):
        for page in self.PAGES:
            html = (ADMIN / page).read_text(encoding="utf-8")
            self.assertIn("../shared/admin-panel.js", html, page)
            self.assertIn("../css/admin-panel.css", html, page)

    def test_admin_code_does_not_use_browser_storage_or_placeholders(self):
        banned = [r"localStorage", r"sessionStorage", r"indexedDB", r"document\.cookie",
                  r"Not connected", r"not connected yet", r"API unavailable", r"Demo", r"demo-data",
                  r"Coming soon", r"TODO", r"lorem", r"placeholder button"]
        sources = [*ADMIN.rglob("*.html"), *ADMIN.rglob("*.js"), SHARED / "admin-panel.js"]
        for source in sources:
            text = source.read_text(encoding="utf-8")
            for pattern in banned:
                self.assertIsNone(re.search(pattern, text), f"{source.name} contains {pattern!r}")

    def test_demo_mode_is_not_offered_on_the_admin_sign_in_page(self):
        html = (ADMIN / "login.html").read_text(encoding="utf-8")
        self.assertNotIn("demo", html.lower())


if __name__ == "__main__":
    unittest.main()
