"""Checkout details (name, phone, instructions) sent with an order, and the request fingerprint.

The fingerprint lets the server tell a genuine retry (same key, same request) from a reused key
that now carries a different order. It covers the items and the details, so changing either one
makes a new request.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from app.services.errors import OrderError

NAME_MAX_LENGTH = 100
INSTRUCTIONS_MAX_LENGTH = 500

# Indian mobile numbers: 10 digits starting 6-9, optionally with +91. Spaces and hyphens are allowed.
_PHONE_PATTERN = re.compile(r"^(?:\+91)?[6-9]\d{9}$")
_SEPARATORS = re.compile(r"[\s-]")


@dataclass(frozen=True)
class CustomerDetails:
    name: str | None = None
    phone: str | None = None
    instructions: str | None = None


def _invalid(message):
    return OrderError("INVALID_CUSTOMER_DETAILS", message, 400)


def _text(value, label, max_length):
    if value is None:
        return None
    if not isinstance(value, str):
        raise _invalid(f"{label} must be text.")
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise _invalid(f"{label} can be at most {max_length} characters.")
    return cleaned


def normalize_phone(value):
    """Return the number as +91XXXXXXXXXX, or None when no number was given."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise _invalid("Phone number must be text.")
    compact = _SEPARATORS.sub("", value.strip())
    if not compact:
        return None
    if not _PHONE_PATTERN.fullmatch(compact):
        raise _invalid("Enter a valid 10-digit mobile number.")
    return "+91" + compact[-10:]


def parse_customer_details(payload):
    """Read and validate the optional checkout fields from a request body. Raises OrderError."""
    return CustomerDetails(
        name=_text(payload.get("customer_name"), "Name", NAME_MAX_LENGTH),
        phone=normalize_phone(payload.get("customer_phone")),
        instructions=_text(payload.get("instructions"), "Special instructions", INSTRUCTIONS_MAX_LENGTH),
    )


def request_fingerprint(requested_items, customer):
    """SHA-256 over the sorted (menu_item_id, quantity) pairs and the checkout details.

    requested_items is the list returned by normalize_requested_items. Its order does not matter.
    """
    payload = {
        "items": sorted([int(menu_id), int(quantity)] for menu_id, quantity in requested_items),
        "name": customer.name,
        "phone": customer.phone,
        "instructions": customer.instructions,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
