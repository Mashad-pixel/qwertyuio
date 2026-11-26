"""Delivers password-recovery codes. The code itself is never written to logs in production."""

import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

logger = logging.getLogger(__name__)


class DeliveryError(Exception):
    """The code could not be delivered. The caller logs this and still answers the user generically."""


def send_recovery_code(email, code):
    config = current_app.config
    mode = config["RECOVERY_DELIVERY"]
    minutes = config["RECOVERY_CODE_MINUTES"]

    if mode == "memory":
        # Tests read codes from here. Never reachable outside TestingConfig.
        current_app.extensions.setdefault("recovery_outbox", []).append({"to": email, "code": code})
        return

    if mode == "console":
        if not config.get("ALLOW_CONSOLE_DELIVERY"):
            raise DeliveryError("console delivery is not allowed in this environment")
        logger.warning("DEVELOPMENT ONLY - recovery code for %s: %s", email, code)
        return

    if mode != "smtp":
        raise DeliveryError(f"unknown RECOVERY_DELIVERY mode: {mode}")

    if not config.get("SMTP_HOST"):
        raise DeliveryError("SMTP_HOST is not set")

    message = EmailMessage()
    message["Subject"] = "Your trayUP password reset code"
    message["From"] = config["SMTP_FROM"]
    message["To"] = email
    message.set_content(
        f"Your verification code is {code}.\n\n"
        f"It expires in {minutes} minutes. If you did not ask to reset your password, "
        "you can ignore this email. Never share this code with anyone."
    )
    try:
        with smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"], timeout=10) as smtp:
            if config["SMTP_USE_TLS"]:
                smtp.starttls()
            if config["SMTP_USERNAME"]:
                smtp.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise DeliveryError(f"SMTP send failed: {exc.__class__.__name__}") from exc
