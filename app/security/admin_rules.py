"""Pure validation rules for canteen details.

This module does not import Flask or the database, so the rules can be tested on their own.
"""

import re

CANTEEN_NAME_MAX_LENGTH = 80
_HHMM_PATTERN = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def clean_canteen_name(value):
    """Return the name with whitespace collapsed. Raise ValueError with a user-facing message if invalid."""
    if not isinstance(value, str):
        raise ValueError("Must be text.")
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Cannot be empty.")
    if len(cleaned) > CANTEEN_NAME_MAX_LENGTH:
        raise ValueError(f"Must be at most {CANTEEN_NAME_MAX_LENGTH} characters.")
    return cleaned


def clean_hhmm(value):
    """Return a 24-hour HH:MM string, or None when the value is None. Raise ValueError otherwise."""
    if value is None:
        return None
    if not isinstance(value, str) or _HHMM_PATTERN.fullmatch(value.strip()) is None:
        raise ValueError("Use 24-hour HH:MM, for example 08:30.")
    return value.strip()


def check_hours_pair(opens_at, closes_at):
    """Return a message if the hours are inconsistent, otherwise None.

    Hours are set as a pair or cleared together, and closing must come after opening. HH:MM
    strings in zero-padded form compare correctly as text.
    """
    if (opens_at is None) != (closes_at is None):
        return "Set both the opening and closing time, or clear both."
    if opens_at is not None and closes_at is not None and closes_at <= opens_at:
        return "The closing time must be after the opening time."
    return None
