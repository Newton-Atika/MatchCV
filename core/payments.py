import hashlib
import hmac
import os
import requests

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import UserSubscription, PaymentTransaction




PAYSTACK_BASE_URL = "https://api.paystack.co"

import os
import re
import hmac
import hashlib
import logging
from datetime import timedelta

import requests

from django.db import transaction
from django.utils import timezone

from .models import UserSubscription, PaymentTransaction


logger = logging.getLogger(__name__)

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "")
PAYSTACK_CURRENCY="KES"
PAYSTACK_AMOUNT=20000
PAYSTACK_PLAN_DAYS=30

PAYSTACK_BASE_URL = "https://api.paystack.co"


class PaystackError(Exception):
    """Raised when a Paystack API request fails."""


def paystack_request(endpoint, payload=None, method="POST"):
    """
    Make an authenticated request to Paystack.

    Raises PaystackError with the actual Paystack response message
    when the API rejects a request.
    """
    if not PAYSTACK_SECRET_KEY:
        raise PaystackError(
            "PAYSTACK_SECRET_KEY is missing. "
            "Configure your Paystack secret key."
        )

    url = f"{PAYSTACK_BASE_URL}/{endpoint.lstrip('/')}"

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        if method.upper() == "GET":
            response = requests.get(
                url,
                headers=headers,
                timeout=30,
            )
        else:
            response = requests.post(
                url,
                headers=headers,
                json=payload or {},
                timeout=30,
            )

    except requests.exceptions.Timeout as exc:
        raise PaystackError(
            "Paystack did not respond in time. Please try again."
        ) from exc

    except requests.exceptions.RequestException as exc:
        logger.exception("Could not connect to Paystack.")
        raise PaystackError(
            f"Network error while contacting Paystack: {exc}"
        ) from exc

    try:
        data = response.json()
    except ValueError:
        data = {}

    # Paystack can return a useful validation message with HTTP 400.
    if not response.ok or not data.get("status"):
        error_message = (
            data.get("message")
            or data.get("error")
            or response.text
            or "Unknown Paystack error"
        )

        logger.error(
            "Paystack API error. Endpoint=%s HTTP=%s Response=%s",
            endpoint,
            response.status_code,
            response.text[:2000],
        )

        raise PaystackError(
            f"Paystack rejected the request "
            f"(HTTP {response.status_code}): {error_message}"
        )

    return data.get("data", {})


def normalize_kenyan_phone(phone):
    """
    Convert common Kenyan phone formats to +254XXXXXXXXX.
    """
    phone = re.sub(r"[\s\-()]", "", str(phone or ""))

    if phone.startswith("+"):
        phone = phone[1:]

    if phone.startswith("0") and len(phone) == 10:
        phone = "254" + phone[1:]

    elif phone.startswith("254") and len(phone) == 12:
        pass

    else:
        raise ValueError(
            "Enter a valid Kenyan mobile number, "
            "for example 0712345678 or +254712345678."
        )

    if not re.fullmatch(r"254[17]\d{8}", phone):
        raise ValueError(
            "Enter a valid Kenyan mobile number, "
            "for example 0712345678 or +254712345678."
        )

    return f"+{phone}"


def verify_webhook_signature(request):
    """
    Verify that a webhook request was signed using the
    configured Paystack secret key.
    """
    signature = request.headers.get("x-paystack-signature", "")

    if not signature or not PAYSTACK_SECRET_KEY:
        return False

    expected_signature = hmac.new(
        PAYSTACK_SECRET_KEY.encode("utf-8"),
        request.body,
        hashlib.sha512,
    ).hexdigest()

    return hmac.compare_digest(signature, expected_signature)


def confirm_and_activate(reference):
    """
    Verify a transaction directly with Paystack.

    Activate the user's one-time subscription only after
    Paystack confirms the payment and the amount/currency match.
    """
    payment = PaymentTransaction.objects.filter(
        reference=reference
    ).select_related("user").first()

    if not payment:
        return False, "Payment transaction was not found."

    if payment.status == "success":
        subscription = UserSubscription.objects.filter(
            user=payment.user
        ).first()

        if subscription and subscription.has_paid_access():
            return True, "Your payment has already been confirmed."

    try:
        result = paystack_request(
            f"transaction/verify/{reference}",
            method="GET",
        )
    except PaystackError as exc:
        return False, str(exc)

    transaction_status = result.get("status")
    paid_amount = result.get("amount")
    paid_currency = result.get("currency")

    if transaction_status != "success":
        gateway_message = (
            result.get("gateway_response")
            or result.get("message")
            or f"Payment status: {transaction_status}"
        )

        payment.gateway_message = str(gateway_message)[:500]

        if transaction_status in ("failed", "abandoned"):
            payment.status = "failed"

        payment.save(
            update_fields=["status", "gateway_message"]
        )

        return False, str(gateway_message)

    if paid_amount != payment.amount:
        payment.gateway_message = (
            "Verified payment amount does not match the expected amount."
        )
        payment.save(update_fields=["gateway_message"])
        return False, payment.gateway_message

    if paid_currency != payment.currency:
        payment.gateway_message = (
            "Verified payment currency does not match the expected currency."
        )
        payment.save(update_fields=["gateway_message"])
        return False, payment.gateway_message

    now = timezone.now()

    with transaction.atomic():
        payment = PaymentTransaction.objects.select_for_update().get(
            pk=payment.pk
        )

        subscription, _ = UserSubscription.objects.get_or_create(
            user=payment.user
        )

        subscription = UserSubscription.objects.select_for_update().get(
            pk=subscription.pk
        )

        # Avoid extending the same transaction more than once.
        if payment.status != "success":
            start_from = subscription.active_until

            if not start_from or start_from < now:
                start_from = now

            subscription.active_until = (
                start_from + timedelta(days=PAYSTACK_PLAN_DAYS)
            )
            subscription.status = "active"
            subscription.last_payment_reference = reference

            payment.status = "success"
            payment.gateway_message = "Payment successfully verified."
            payment.paid_at = now

            subscription.save(
                update_fields=[
                    "active_until",
                    "status",
                    "last_payment_reference",
                ]
            )

            payment.save(
                update_fields=[
                    "status",
                    "gateway_message",
                    "paid_at",
                ]
            )

    return True, "Payment successful. Your 30-day access is now active."
