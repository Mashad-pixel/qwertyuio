"""Server-side Firebase Realtime Database mirror for TrayUP orders.

The relational SQL database remains the source of truth. Firebase is a
server-managed live mirror; browser clients must not write order/payment data.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

try:
    import firebase_admin
    from firebase_admin import credentials, db as firebase_db
except ImportError:  # Keep Firebase optional for local tests and disabled deployments.
    firebase_admin = None
    credentials = None
    firebase_db = None

from flask import current_app

_APP_EXTENSION_KEY = "trayup_firebase_app"


def initialize_firebase(app):
    """Initialize Firebase Admin only when explicitly enabled in configuration."""
    if not app.config.get("FIREBASE_ENABLED", False):
        app.extensions[_APP_EXTENSION_KEY] = None
        app.logger.info("Firebase Realtime Database integration is disabled.")
        return

    if firebase_admin is None:
        raise RuntimeError("Firebase is enabled but firebase-admin is not installed. Run pip install -r requirements.txt.")

    database_url = (app.config.get("FIREBASE_DATABASE_URL") or "").strip()
    credential_path = app.config.get("FIREBASE_SERVICE_ACCOUNT_PATH")
    if not database_url:
        raise RuntimeError("FIREBASE_ENABLED=true requires FIREBASE_DATABASE_URL.")
    if not credential_path or not os.path.isfile(credential_path):
        raise RuntimeError(
            "Firebase service-account JSON was not found. Set "
            "FIREBASE_SERVICE_ACCOUNT_PATH to your local key file."
        )

    app_name = "trayup-admin-sdk"
    try:
        firebase_app = firebase_admin.get_app(app_name)
    except ValueError:
        credential = credentials.Certificate(credential_path)
        firebase_app = firebase_admin.initialize_app(
            credential,
            {"databaseURL": database_url},
            name=app_name,
        )
    app.extensions[_APP_EXTENSION_KEY] = firebase_app
    app.logger.info("Firebase Admin SDK initialized for TrayUP.")


def firebase_is_enabled() -> bool:
    return bool(current_app.extensions.get(_APP_EXTENSION_KEY))


def _order_payload(order):
    """Return a deliberately limited payload: no phone, email, tokens or secrets."""
    created_at = order.created_at
    updated_at = order.updated_at
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if updated_at and updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    items = [{
        "menu_item_id": item.menu_item_id,
        "name": item.item_name_snapshot,
        "quantity": item.quantity,
    } for item in order.items]

    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "order_status": order.order_status,
        "payment_status": order.payment_status,
        "total_paise": order.total_paise,
        "items": items,
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def sync_order_to_firebase(order):
    """Mirror a committed order. Firebase failure never rolls back SQL/payment."""
    if not firebase_is_enabled():
        return False

    try:
        payload = _order_payload(order)
        firebase_app = current_app.extensions[_APP_EXTENSION_KEY]
        firebase_db.reference(f"orders/{order.id}", app=firebase_app).set(payload)

        is_active_kitchen_order = (
            order.payment_status == "paid"
            and order.order_status in {"received", "preparing", "ready"}
        )
        kitchen_ref = firebase_db.reference(f"kitchen/orders/{order.id}", app=firebase_app)
        if is_active_kitchen_order:
            kitchen_ref.set(payload)
        else:
            kitchen_ref.delete()
        return True
    except Exception:
        current_app.logger.exception(
            "Could not mirror TrayUP order %s to Firebase; SQL remains authoritative.",
            getattr(order, "id", "unknown"),
        )
        return False


def firebase_connection_status():
    """Perform a small authenticated write/delete to verify actual RTDB access."""
    if not firebase_is_enabled():
        return {"enabled": False, "connected": False, "message": "Firebase integration is disabled."}
    try:
        firebase_app = current_app.extensions[_APP_EXTENSION_KEY]
        health_ref = firebase_db.reference(
            f"_system/health_checks/{uuid.uuid4().hex}", app=firebase_app
        )
        health_ref.set({
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "service": "trayup-backend",
        })
        health_ref.delete()
        return {
            "enabled": True,
            "connected": True,
            "message": "Authenticated read/write access to Firebase Realtime Database is working.",
        }
    except Exception:
        current_app.logger.exception("Firebase connection health check failed.")
        return {
            "enabled": True,
            "connected": False,
            "message": "Firebase health check failed. Check the database URL, service-account key and database permissions.",
        }
