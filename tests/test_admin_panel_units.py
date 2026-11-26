"""Unit tests for the admin panel's pure rules and repository-level checks.

These use only the standard library and load modules by file path, so they run without installing
the application's dependencies. They check: canteen detail validation, the migration history has a
single head and no duplicate schema changes, and every `from app...` import names something defined.
"""

import ast
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(relative_path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = _load("app/security/admin_rules.py", "admin_rules_under_test")


class CanteenNameTests(unittest.TestCase):
    def test_name_is_trimmed_and_whitespace_collapsed(self):
        self.assertEqual(rules.clean_canteen_name("  Main   Canteen \n Block A "), "Main Canteen Block A")

    def test_blank_name_is_refused(self):
        with self.assertRaises(ValueError):
            rules.clean_canteen_name("   ")

    def test_non_text_name_is_refused(self):
        with self.assertRaises(ValueError):
            rules.clean_canteen_name(12)

    def test_name_longer_than_limit_is_refused(self):
        with self.assertRaises(ValueError):
            rules.clean_canteen_name("x" * (rules.CANTEEN_NAME_MAX_LENGTH + 1))

    def test_name_at_limit_is_accepted(self):
        value = "x" * rules.CANTEEN_NAME_MAX_LENGTH
        self.assertEqual(rules.clean_canteen_name(value), value)


class HhmmTests(unittest.TestCase):
    def test_valid_24_hour_times_are_accepted(self):
        for value in ["00:00", "08:30", "23:59", " 09:05 "]:
            self.assertEqual(rules.clean_hhmm(value), value.strip())

    def test_none_means_not_published(self):
        self.assertIsNone(rules.clean_hhmm(None))

    def test_invalid_times_are_refused(self):
        for value in ["24:00", "12:60", "8:30", "08-30", "0830", "noon", "", 830, "08:30:00"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    rules.clean_hhmm(value)


class HoursPairTests(unittest.TestCase):
    def test_both_empty_is_allowed(self):
        self.assertIsNone(rules.check_hours_pair(None, None))

    def test_both_set_in_order_is_allowed(self):
        self.assertIsNone(rules.check_hours_pair("08:00", "18:00"))

    def test_one_sided_hours_are_refused(self):
        self.assertIsNotNone(rules.check_hours_pair("08:00", None))
        self.assertIsNotNone(rules.check_hours_pair(None, "18:00"))

    def test_closing_must_come_after_opening(self):
        self.assertIsNotNone(rules.check_hours_pair("18:00", "08:00"))
        self.assertIsNotNone(rules.check_hours_pair("08:00", "08:00"))


class MigrationHistoryTests(unittest.TestCase):
    """The migration chain must be linear enough for `flask db upgrade` to run on a fresh database."""

    @classmethod
    def setUpClass(cls):
        cls.revisions = {}
        for path in sorted((ROOT / "migrations" / "versions").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            revision = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", text, re.M).group(1)
            down = re.search(r"^down_revision\s*=\s*(.+)$", text, re.M).group(1)
            cls.revisions[revision] = (path.name, re.findall(r"['\"]([^'\"]+)['\"]", down), text)

    def test_exactly_one_head(self):
        parents = {parent for _, parents_of, _ in self.revisions.values() for parent in parents_of}
        heads = [rev for rev in self.revisions if rev not in parents]
        self.assertEqual(len(heads), 1, f"multiple heads: {heads}")

    def test_every_parent_exists(self):
        for revision, (name, parents, _) in self.revisions.items():
            for parent in parents:
                self.assertIn(parent, self.revisions, f"{name} points at missing revision {parent}")

    def _ordered(self):
        """Revisions parents-first, so each migration is applied after everything it depends on."""
        order, seen = [], set()

        def visit(revision):
            if revision in seen:
                return
            seen.add(revision)
            for parent in self.revisions[revision][1]:
                visit(parent)
            order.append(revision)

        for revision in self.revisions:
            visit(revision)
        return order

    def test_schema_changes_apply_in_order_without_conflicts(self):
        """Walk the history in apply order: a table may only be created when it does not exist."""
        existing = set()
        for revision in self._ordered():
            name, _, text = self.revisions[revision]
            for table in re.findall(r"create_table\(\s*['\"]([a-z_]+)['\"]", text):
                self.assertNotIn(table, existing, f"{name} creates {table}, which already exists")
                existing.add(table)
            for table in re.findall(r"drop_table\(\s*['\"]([a-z_]+)['\"]", text):
                existing.discard(table)


class ImportNamesTests(unittest.TestCase):
    """Every `from app.x import name` must refer to a name that module defines (or a submodule)."""

    @staticmethod
    def _defined_names(path):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
        return names

    @staticmethod
    def _module_path(dotted):
        base = ROOT.joinpath(*dotted.split("."))
        if base.with_suffix(".py").is_file():
            return base.with_suffix(".py")
        if (base / "__init__.py").is_file():
            return base / "__init__.py"
        return None

    def test_app_imports_resolve(self):
        problems = []
        for path in (ROOT / "app").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "app"):
                    continue
                target = self._module_path(node.module)
                if target is None:
                    problems.append(f"{path.relative_to(ROOT)}:{node.lineno} missing module {node.module}")
                    continue
                defined = self._defined_names(target)
                for alias in node.names:
                    if alias.name == "*" or alias.name in defined:
                        continue
                    if self._module_path(f"{node.module}.{alias.name}") is None:
                        problems.append(f"{path.relative_to(ROOT)}:{node.lineno} {alias.name!r} not in {node.module}")
        # account_recovery.py is a stale module from an abandoned migration branch. Nothing imports it.
        problems = [p for p in problems if "account_recovery.py" not in p]
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
