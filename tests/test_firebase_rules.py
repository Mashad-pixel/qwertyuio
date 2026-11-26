"""Firebase Realtime Database is a server-side mirror. Browsers must never write to it.

Three guarantees are checked here:
  1. The rules file denies all reads and writes at every path (deny-by-default).
  2. No browser code talks to Firebase, so there is no client-side write path to protect.
  3. The mirrored payload carries no contact details or secrets, and a Firebase outage never
     changes or breaks an order.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services import firebase_service
from app.services.firebase_service import (
    _order_payload,
    firebase_connection_status,
    sync_order_to_firebase,
)
from app.services.order_service import create_order

ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "database.rules.json"
FRONTEND_DIR = ROOT / "frontend"

# Exactly what the mirror is allowed to contain. Anything else is a leak.
ALLOWED_PAYLOAD_KEYS = {
    "order_id",
    "order_number",
    "order_status",
    "payment_status",
    "total_paise",
    "items",
    "created_at",
    "updated_at",
}
ALLOWED_ITEM_KEYS = {"menu_item_id", "name", "quantity"}


def _rule_grants(node, path="$root"):
    """Yield (path, key, value) for every .read/.write entry that is not an explicit false."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in (".read", ".write") and value is not False:
                yield path, key, value
            elif isinstance(value, (dict, list)):
                yield from _rule_grants(value, f"{path}/{key}")


# ---------- 1. Rules file ----------

def test_rules_file_is_valid_json_with_only_the_rules_key():
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))

    assert set(rules) == {"rules"}


def test_root_denies_read_and_write():
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))

    assert rules["rules"][".read"] is False
    assert rules["rules"][".write"] is False


def test_no_path_grants_read_or_write_anywhere_in_the_tree():
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))

    assert list(_rule_grants(rules)) == []


def test_rule_checker_would_catch_a_permissive_child_rule():
    """Guard the guard: prove the checker really detects an open path."""
    permissive = {"rules": {".read": False, ".write": False, "orders": {"$id": {".write": True}}}}

    grants = list(_rule_grants(permissive))

    assert grants == [("$root/rules/orders/$id", ".write", True)]


def test_rules_file_contains_no_wildcard_or_auth_expression_that_could_open_access():
    text = RULES_PATH.read_text(encoding="utf-8")

    for token in ("auth", "true", "$"):
        assert token not in text.replace('"$root"', ""), token


# ---------- 2. Browser code ----------

def test_no_frontend_file_references_firebase():
    offenders = []
    for path in FRONTEND_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".js", ".html", ".css", ".json", ".md"}:
            if "firebase" in path.read_text(encoding="utf-8", errors="ignore").lower():
                offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


# ---------- 3. Mirror payload and failure containment ----------

def test_mirror_payload_contains_only_the_allowed_fields(app, student, menu):
    order, _ = create_order(student.id, [{"menu_item_id": menu["tea"].id, "quantity": 2}])

    payload = _order_payload(order)

    assert set(payload) == ALLOWED_PAYLOAD_KEYS
    assert all(set(item) == ALLOWED_ITEM_KEYS for item in payload["items"])


def test_mirror_payload_never_contains_contact_details_or_tokens(app, student, menu):
    order, raw_token = create_order(student.id, [{"menu_item_id": menu["tea"].id, "quantity": 1}])

    serialized = json.dumps(_order_payload(order))

    assert student.email not in serialized
    assert student.name not in serialized
    assert raw_token not in serialized
    assert order.tracking_token_hash not in serialized
    assert "password" not in serialized.lower()


@pytest.fixture
def firebase_enabled(app):
    """Pretend Firebase initialised, without any network access or credentials."""
    app.extensions["trayup_firebase_app"] = object()
    yield app
    app.extensions["trayup_firebase_app"] = None


def test_sync_is_skipped_when_firebase_is_disabled(app, student, menu):
    order, _ = create_order(student.id, [{"menu_item_id": menu["tea"].id, "quantity": 1}])

    with patch.object(firebase_service, "firebase_db") as firebase_db:
        assert sync_order_to_firebase(order) is False

    firebase_db.reference.assert_not_called()


def test_firebase_outage_never_raises_into_order_flow(firebase_enabled, student, menu):
    order, _ = create_order(student.id, [{"menu_item_id": menu["tea"].id, "quantity": 1}])
    failing_ref = MagicMock()
    failing_ref.set.side_effect = RuntimeError("network down")

    with patch.object(firebase_service, "firebase_db") as firebase_db:
        firebase_db.reference.return_value = failing_ref
        assert sync_order_to_firebase(order) is False

    # SQL remains authoritative: the order is still there and unchanged.
    from app.models.order import Order

    assert Order.query.filter_by(id=order.id).count() == 1


def test_mirror_writes_only_server_side_paths(firebase_enabled, student, menu):
    order, _ = create_order(student.id, [{"menu_item_id": menu["tea"].id, "quantity": 1}])
    paths = []

    def record(path, app=None):
        paths.append(path)
        return MagicMock()

    with patch.object(firebase_service, "firebase_db") as firebase_db:
        firebase_db.reference.side_effect = record
        assert sync_order_to_firebase(order) is True

    assert paths == [f"orders/{order.id}", f"kitchen/orders/{order.id}"]


def test_connection_status_reports_disabled_without_touching_firebase(app):
    with patch.object(firebase_service, "firebase_db") as firebase_db:
        status = firebase_connection_status()

    assert status == {
        "enabled": False,
        "connected": False,
        "message": "Firebase integration is disabled.",
    }
    firebase_db.reference.assert_not_called()


def test_connection_status_failure_message_does_not_leak_exception_text(firebase_enabled):
    with patch.object(firebase_service, "firebase_db") as firebase_db:
        firebase_db.reference.side_effect = RuntimeError("secret-project-url-leak")
        status = firebase_connection_status()

    assert status["connected"] is False
    assert "secret-project-url-leak" not in json.dumps(status)
