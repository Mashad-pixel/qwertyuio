"""Validation rules for student and staff account details."""

import re

MAX_NAME_LENGTH = 100
MAX_EMAIL_LENGTH = 120
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

_EMAIL_PATTERN = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


def normalize_email(raw_email):
    """Normalize email addresses before uniqueness checks."""
    return raw_email.strip().lower()


def is_valid_email(email):
    return len(email) <= MAX_EMAIL_LENGTH and _EMAIL_PATTERN.fullmatch(email) is not None


def is_valid_name(name):
    return 0 < len(name) <= MAX_NAME_LENGTH


def password_problem(password):
    """Return a message for an unacceptable password, or None."""
    if not isinstance(password, str):
        return "Password is required."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
    if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        return "Password must include at least one letter and one number."
    return None
