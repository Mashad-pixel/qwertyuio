"""Outgoing email for password recovery.

Codes are only written to the log by the "console" backend, which production refuses at startup.
Email addresses are never logged, and failures raise MailError without the message body.
"""

import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


class MailError(Exception):
    """Email could not be sent. Callers must not reveal this to the person asking."""


def mail_configured():
    config = current_app.config
    backend = config.get("MAIL_BACKEND")
    if backend == "smtp":
        return bool(config.get("MAIL_HOST") and config.get("MAIL_FROM"))
    return backend in ("console", "memory")


def send_mail(to_address, subject, body):
    config = current_app.config
    backend = config.get("MAIL_BACKEND")

    if backend == "memory":
        current_app.extensions.setdefault("mail_outbox", []).append(
            {"to": to_address, "subject": subject, "body": body}
        )
        return

    if backend == "console":
        current_app.logger.warning("DEVELOPMENT ONLY - email not sent. Subject: %s\n%s", subject, body)
        return

    if backend != "smtp" or not mail_configured():
        raise MailError("Email is not configured.")

    message = EmailMessage()
    message["From"] = config["MAIL_FROM"]
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(config["MAIL_HOST"], config["MAIL_PORT"], timeout=10) as smtp:
            if config.get("MAIL_USE_TLS"):
                smtp.starttls(context=ssl.create_default_context())
            if config.get("MAIL_USERNAME"):
                smtp.login(config["MAIL_USERNAME"], config.get("MAIL_PASSWORD", ""))
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError("Email could not be sent.") from exc
