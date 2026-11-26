import razorpay
from requests import RequestException
from razorpay.errors import BadRequestError, GatewayError, ServerError

from flask import current_app

from app.services.errors import OrderError

PROVIDER_ERRORS = (BadRequestError, GatewayError, ServerError, RequestException)


def get_razorpay_client():
    key_id = current_app.config["RAZORPAY_KEY_ID"]
    key_secret = current_app.config["RAZORPAY_KEY_SECRET"]
    if not key_id or not key_secret:
        raise OrderError(
            "PAYMENTS_NOT_CONFIGURED",
            "Online payments are not configured on this server.",
            503,
        )
    return razorpay.Client(auth=(key_id, key_secret))
