from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from docx import Document
from pypdf import PdfReader

from .models import CVScan, Profile
from .matching_engine import analyze_cv_against_job





import json
import logging
import uuid


import json
import logging
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import UserSubscription, PaymentTransaction
from .payments import (
    PAYSTACK_AMOUNT,
    PAYSTACK_CURRENCY,
    PAYSTACK_PLAN_DAYS,
    PaystackError,
    paystack_request,
    normalize_kenyan_phone,
    confirm_and_activate,
    verify_webhook_signature,
)


logger = logging.getLogger(__name__)


def get_user_subscription(user):
    subscription, _ = UserSubscription.objects.get_or_create(user=user)
    subscription.update_status()
    return subscription


def get_valid_email(user):
    email = (user.email or "").strip()

    if not email:
        raise ValueError(
            "Your account has no email address. "
            "Please update your account before paying."
        )

    try:
        validate_email(email)
    except ValidationError as exc:
        raise ValueError(
            "Your account email address is invalid. "
            "Please update it before paying."
        ) from exc

    return email


@login_required
def subscription(request):
    user_subscription = get_user_subscription(request.user)

    recent_payments = PaymentTransaction.objects.filter(
        user=request.user
    ).order_by("-created_at")[:5]

    context = {
        "subscription": user_subscription,
        "recent_payments": recent_payments,
        "amount": PAYSTACK_AMOUNT / 100,
        "currency": PAYSTACK_CURRENCY,
        "has_paid_access": user_subscription.has_paid_access(),
        "free_scan_available": not user_subscription.free_scan_used,
    }

    return render(request, "core/subscription.html", context)


@login_required
@require_POST
def initialize_card_payment(request):
    user_subscription = get_user_subscription(request.user)

    if user_subscription.has_paid_access():
        messages.info(request, "Your plan is already active.")
        return redirect("subscription")

    payment = None

    try:
        email = get_valid_email(request.user)
        reference = f"CVMCARD{uuid.uuid4().hex}"

        payment = PaymentTransaction.objects.create(
            user=request.user,
            reference=reference,
            amount=PAYSTACK_AMOUNT,
            currency=PAYSTACK_CURRENCY,
            payment_method="card",
            status="pending",
        )

        callback_url = request.build_absolute_uri(
            reverse("payment_callback")
        )

        result = paystack_request(
            "transaction/initialize",
            {
                "email": email,
                "amount": str(PAYSTACK_AMOUNT),
                "currency": PAYSTACK_CURRENCY,
                "reference": reference,
                "callback_url": callback_url,
                "channels": ["card"],
                "metadata": {
                    "user_id": request.user.id,
                    "payment_reference": reference,
                    "purpose": f"CVMatch {PAYSTACK_PLAN_DAYS}-day access",
                },
            },
        )

        authorization_url = result.get("authorization_url")

        if not authorization_url:
            raise PaystackError(
                f"Paystack did not return a checkout URL. Response: {result}"
            )

        return redirect(authorization_url)

    except Exception as exc:
        logger.exception("Card payment initialization failed.")

        if payment:
            payment.status = "failed"
            payment.gateway_message = str(exc)[:500]
            payment.save(
                update_fields=["status", "gateway_message"]
            )

        messages.error(
            request,
            f"Unable to start card payment: {exc}",
        )
        return redirect("subscription")


@login_required
@require_POST
def initialize_mpesa_payment(request):
    user_subscription = get_user_subscription(request.user)

    if user_subscription.has_paid_access():
        messages.info(request, "Your plan is already active.")
        return redirect("subscription")

    payment = None

    try:
        email = get_valid_email(request.user)
        phone = normalize_kenyan_phone(
            request.POST.get("phone_number", "")
        )

        reference = f"CVMPESA{uuid.uuid4().hex}"

        payment = PaymentTransaction.objects.create(
            user=request.user,
            reference=reference,
            amount=PAYSTACK_AMOUNT,
            currency=PAYSTACK_CURRENCY,
            payment_method="mpesa",
            phone_number=phone,
            status="pending",
        )

        result = paystack_request(
            "charge",
            {
                "email": email,
                "amount": str(PAYSTACK_AMOUNT),
                "currency": PAYSTACK_CURRENCY,
                "reference": reference,
                "mobile_money": {
                    "phone": phone,
                    "provider": "mpesa",
                },
                "metadata": {
                    "user_id": request.user.id,
                    "payment_reference": reference,
                    "purpose": f"CVMatch {PAYSTACK_PLAN_DAYS}-day access",
                },
            },
        )

        display_message = (
            result.get("display_text")
            or result.get("message")
            or "Please check your phone and complete the payment."
        )

        payment.gateway_message = display_message
        payment.save(update_fields=["gateway_message"])

        return render(
            request,
            "core/payment_pending.html",
            {
                "payment": payment,
                "display_message": display_message,
            },
        )

    except Exception as exc:
        logger.exception("M-Pesa payment initialization failed.")

        if payment:
            payment.status = "failed"
            payment.gateway_message = str(exc)[:500]
            payment.save(
                update_fields=["status", "gateway_message"]
            )

        messages.error(
            request,
            f"Unable to start M-Pesa payment: {exc}",
        )
        return redirect("subscription")


@login_required
def payment_callback(request):
    reference = (
        request.GET.get("reference")
        or request.GET.get("trxref")
    )

    if not reference:
        messages.error(
            request,
            "Payment reference was not received.",
        )
        return redirect("subscription")

    payment = PaymentTransaction.objects.filter(
        reference=reference,
        user=request.user,
    ).first()

    if not payment:
        messages.error(
            request,
            "We could not find this payment.",
        )
        return redirect("subscription")

    try:
        success, message = confirm_and_activate(reference)

        if success:
            messages.success(request, message)
        else:
            messages.warning(
                request,
                message or "Payment has not yet been confirmed.",
            )

    except Exception:
        logger.exception(
            "Payment callback verification failed: %s",
            reference,
        )
        messages.warning(
            request,
            "We could not verify your payment right now. "
            "Please check its status again shortly.",
        )

    return redirect("subscription")


@login_required
def check_payment_status(request, reference):
    payment = PaymentTransaction.objects.filter(
        reference=reference,
        user=request.user,
    ).first()

    if not payment:
        return JsonResponse(
            {
                "success": False,
                "message": "Payment not found.",
            },
            status=404,
        )

    try:
        if payment.status != "success":
            success, message = confirm_and_activate(reference)
        else:
            success = True
            message = "Your payment has been confirmed."

    except Exception:
        logger.exception(
            "Payment status check failed: %s",
            reference,
        )
        success = False
        message = "Unable to verify payment at this time."

    payment.refresh_from_db()
    user_subscription = get_user_subscription(request.user)

    return JsonResponse(
        {
            "success": success,
            "payment_status": payment.status,
            "active": user_subscription.has_paid_access(),
            "active_until": (
                user_subscription.active_until.isoformat()
                if user_subscription.active_until
                else None
            ),
            "message": message,
        }
    )


@csrf_exempt
@require_POST
def paystack_webhook(request):
    if not verify_webhook_signature(request):
        return HttpResponse(status=400)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponse(status=400)

    event = payload.get("event")
    data = payload.get("data", {})

    if event == "charge.success":
        reference = data.get("reference")

        if reference:
            payment = PaymentTransaction.objects.filter(
                reference=reference
            ).first()

            if payment:
                try:
                    confirm_and_activate(reference)
                except Exception:
                    logger.exception(
                        "Webhook verification failed: %s",
                        reference,
                    )
                    return HttpResponse(status=500)

    return HttpResponse(status=200)
# ============================================================
# LANDING PAGE
# ============================================================

def landing_page(request):
    return render(
        request,
        "core/landing.html"
    )


def privacy_policy(request):
    return render(request, "core/privacy_policy.html")
# ============================================================
# ACCOUNT
# ============================================================

def account(request):
    if request.user.is_authenticated:
        return redirect("account_dashboard")

    return render(
        request,
        "core/account.html"
    )

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.shortcuts import render, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


def login_view(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        User = get_user_model()
        username_field = User.USERNAME_FIELD

        credentials = None

        if username_field == "email":
            credentials = {
                "email": email,
                "password": password
            }
        else:
            user_obj = User.objects.filter(
                email__iexact=email
            ).first()

            if user_obj:
                credentials = {
                    username_field: user_obj.get_username(),
                    "password": password
                }

        user = None

        if credentials and email and password:
            user = authenticate(request, **credentials)

        if user is not None:
            login(request, user)

            next_url = request.POST.get("next") or request.GET.get("next")

            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure()
            ):
                return redirect(next_url)

            return redirect(settings.LOGIN_REDIRECT_URL)

        messages.error(
            request,
            "Invalid email or password. Please try again."
        )

    return render(request, "core/login.html")


@require_POST
def logout_view(request):
    logout(request)

    messages.success(
        request,
        "You have been logged out successfully."
    )

    return redirect("login")
# ============================================================
# REGISTER
# ============================================================

def register(request):

    if request.user.is_authenticated:
        return redirect("account_dashboard")

    if request.method == "POST":

        full_name = request.POST.get(
            "full_name",
            ""
        ).strip()

        email = request.POST.get(
            "email",
            ""
        ).strip().lower()

        phone = request.POST.get(
            "phone",
            ""
        ).strip()

        password = request.POST.get(
            "password",
            ""
        )

        confirm_password = request.POST.get(
            "confirm_password",
            ""
        )

        terms = request.POST.get(
            "terms"
        )

        # ----------------------------------------------------
        # Validation
        # ----------------------------------------------------

        if not full_name:
            messages.error(
                request,
                "Please enter your full name."
            )
            return redirect("register")

        if not email:
            messages.error(
                request,
                "Please enter your email address."
            )
            return redirect("register")

        if not password:
            messages.error(
                request,
                "Please create a password."
            )
            return redirect("register")

        if password != confirm_password:
            messages.error(
                request,
                "Passwords do not match."
            )
            return redirect("register")

        if len(password) < 8:
            messages.error(
                request,
                "Your password must contain at least 8 characters."
            )
            return redirect("register")

        if not terms:
            messages.error(
                request,
                "Please accept the terms and conditions."
            )
            return redirect("register")

        if User.objects.filter(
            username=email
        ).exists():

            messages.error(
                request,
                "An account with this email already exists."
            )
            return redirect("register")

        # ----------------------------------------------------
        # Create account
        # ----------------------------------------------------

        try:

            with transaction.atomic():

                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    first_name=full_name,
                )

                Profile.objects.create(
                    user=user,
                    phone=phone,
                )

                login(
                    request,
                    user
                )

            messages.success(
                request,
                "Your account has been created."
            )

            return redirect(
                "account_dashboard"
            )

        except Exception as exc:

            messages.error(
                request,
                f"Unable to create your account: {exc}"
            )

            return redirect(
                "register"
            )

    return render(
        request,
        "core/register.html"
    )


# ============================================================
# DASHBOARD
# ============================================================

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import CVScan, UserSubscription, PaymentTransaction


@login_required
def account_dashboard(request):
    subscription, _ = UserSubscription.objects.get_or_create(
        user=request.user
    )
    subscription.update_status()

    scans = CVScan.objects.filter(
        user=request.user
    ).order_by("-created_at")

    payments = PaymentTransaction.objects.filter(
        user=request.user
    ).order_by("-created_at")

    context = {
        "subscription": subscription,
        "has_paid_access": subscription.has_paid_access(),
        "scans": scans,
        "payments": payments,
    }

    return render(request, "core/account_dashboard.html", context)


# ============================================================
# IMPORTS FOR CV TEXT EXTRACTION
# ============================================================

import io
import re

from pypdf import PdfReader
from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.table import Table

from django.core.exceptions import ValidationError


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_extracted_text(text):
    """
    Minimal text cleaning.

    Preserve the extracted words, paragraph order,
    line breaks, bullets and section structure.
    """

    if not text:
        return ""

    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = text.replace("\u00a0", " ")

    # Remove excessive blank lines without merging paragraphs.
    text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)

    # Remove trailing spaces on each line.
    text = "\n".join(
        line.rstrip()
        for line in text.split("\n")
    )

    return text.strip()


# ============================================================
# PDF TEXT EXTRACTION
# ============================================================

def extract_pdf_text(file):
    """
    Extract PDF text using pypdf.

    First try layout mode to retain approximate
    positions and line structure.

    Fall back to ordinary text extraction if layout
    mode is unsupported or fails.
    """

    try:
        file.seek(0)

        pdf_bytes = file.read()

        if not pdf_bytes:
            raise ValidationError(
                "The uploaded PDF is empty."
            )

        reader = PdfReader(
            io.BytesIO(pdf_bytes),
            strict=False
        )

        extracted_pages = []

        for page_number, page in enumerate(reader.pages):

            page_text = ""

            # Try layout-aware extraction first.
            try:
                page_text = page.extract_text(
                    extraction_mode="layout"
                ) or ""

            except Exception:
                page_text = ""

            # Fallback to ordinary extraction.
            if not page_text.strip():

                try:
                    page_text = page.extract_text() or ""

                except Exception:
                    page_text = ""

            page_text = clean_extracted_text(
                page_text
            )

            if page_text:
                extracted_pages.append(
                    page_text
                )

        full_text = "\n\n".join(
            extracted_pages
        )

        if not full_text.strip():
            raise ValidationError(
                "No readable text was extracted from this PDF. "
                "The file may be scanned or contain an unsupported "
                "text layer. OCR may be required."
            )

        return full_text

    except ValidationError:
        raise

    except Exception as exc:
        raise ValidationError(
            f"Unable to extract PDF text: {exc}"
        )


# ============================================================
# DOCX TEXT EXTRACTION
# ============================================================

def extract_docx_text(file):
    """
    Extract DOCX paragraphs and tables in their
    original body order.

    Retain paragraph breaks, headings, list text
    and table rows.
    """

    try:
        file.seek(0)

        document = Document(
            io.BytesIO(file.read())
        )

        extracted_parts = []

        body = document.element.body

        for element in body.iterchildren():

            # ------------------------------------------------
            # PARAGRAPHS
            # ------------------------------------------------

            if element.tag == qn("w:p"):

                paragraph = Paragraph(
                    element,
                    document
                )

                text = paragraph.text

                if not text.strip():
                    continue

                style_name = ""

                if paragraph.style:
                    style_name = (
                        paragraph.style.name.lower()
                    )

                # Use existing list formatting when detectable.
                if (
                    "bullet" in style_name
                    or "list" in style_name
                ):
                    text = "• " + text

                extracted_parts.append(
                    text
                )

            # ------------------------------------------------
            # TABLES
            # ------------------------------------------------

            elif element.tag == qn("w:tbl"):

                table = Table(
                    element,
                    document
                )

                table_text = []

                for row in table.rows:

                    row_cells = []

                    for cell in row.cells:

                        cell_paragraphs = []

                        for paragraph in cell.paragraphs:

                            paragraph_text = (
                                paragraph.text.strip()
                            )

                            if paragraph_text:
                                cell_paragraphs.append(
                                    paragraph_text
                                )

                        cell_text = "\n".join(
                            cell_paragraphs
                        )

                        row_cells.append(
                            cell_text
                        )

                    if any(
                        cell.strip()
                        for cell in row_cells
                    ):
                        table_text.append(
                            " | ".join(row_cells)
                        )

                if table_text:
                    extracted_parts.append(
                        "\n".join(table_text)
                    )

        full_text = "\n\n".join(
            extracted_parts
        )

        full_text = clean_extracted_text(
            full_text
        )

        if not full_text:
            raise ValidationError(
                "No readable text was found in this DOCX file."
            )

        return full_text

    except ValidationError:
        raise

    except Exception as exc:
        raise ValidationError(
            f"Unable to extract DOCX text: {exc}"
        )


# ============================================================
# TXT TEXT EXTRACTION
# ============================================================

def extract_txt_text(file):
    """
    Read plain-text CV files while retaining
    their original line and paragraph structure.
    """

    try:
        file.seek(0)

        content = file.read()

        if isinstance(content, str):
            text = content

        else:
            text = None

            for encoding in (
                "utf-8-sig",
                "utf-8",
                "cp1252",
                "latin-1"
            ):
                try:
                    text = content.decode(
                        encoding
                    )
                    break

                except UnicodeDecodeError:
                    continue

            if text is None:
                raise ValidationError(
                    "Unable to decode the TXT file."
                )

        return clean_extracted_text(
            text
        )

    except ValidationError:
        raise

    except Exception as exc:
        raise ValidationError(
            f"Unable to extract TXT text: {exc}"
        )


# ============================================================
# MAIN CV EXTRACTION FUNCTION
# ============================================================

def extract_cv_text(file):
    """
    Select the appropriate extraction function
    based on the uploaded file extension.
    """

    if not file:
        raise ValidationError(
            "Please upload a CV."
        )

    filename = file.name.lower()

    if filename.endswith(".pdf"):
        return extract_pdf_text(file)

    elif filename.endswith(".docx"):
        return extract_docx_text(file)

    elif filename.endswith(".txt"):
        return extract_txt_text(file)

    raise ValidationError(
        "Unsupported file format. "
        "Please upload a PDF, DOCX or TXT file."
    )


# ============================================================
# TERMS OF USE
# ============================================================

def terms_of_use(request):
    return render(
        request,
        "core/terms.html"
    )



# ============================================================
# SCAN CV
# ============================================================

from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.db import transaction

from .models import CVScan, UserSubscription



from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from .models import UserSubscription, CVScan


@login_required(login_url="account")
def scan_cv(request):

    # --------------------------------------------------------
    # GET REQUEST
    # --------------------------------------------------------

    if request.method != "POST":

        return render(
            request,
            "core/scan.html"
        )

    # --------------------------------------------------------
    # CHECK SUBSCRIPTION / FREE SCAN ACCESS
    # --------------------------------------------------------

    subscription, _ = UserSubscription.objects.get_or_create(
        user=request.user
    )

    if not subscription.can_scan():

        messages.warning(
            request,
            "You have used your free scan and your paid plan "
            "is not active. Pay KES 200 to activate 30 days "
            "of CVMatch access."
        )

        return redirect(
            "subscription"
        )

    # --------------------------------------------------------
    # GET INPUTS
    # --------------------------------------------------------

    cv_file = request.FILES.get(
        "cv_file"
    )

    job_description = request.POST.get(
        "job_description",
        ""
    ).strip()

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not cv_file:

        messages.error(
            request,
            "Please upload your CV."
        )

        return redirect(
            "scan_cv"
        )

    if not job_description:

        messages.error(
            request,
            "Please enter the job description."
        )

        return redirect(
            "scan_cv"
        )

    # --------------------------------------------------------
    # EXTRACT CV
    #
    # The actual uploaded file is NOT stored.
    # --------------------------------------------------------

    try:

        cv_text = extract_cv_text(
            cv_file
        )

    except Exception as exc:

        messages.error(
            request,
            f"Unable to read your CV: {exc}"
        )

        return redirect(
            "scan_cv"
        )

    if not cv_text.strip():

        messages.error(
            request,
            "We could not extract readable text from your CV."
        )

        return redirect(
            "scan_cv"
        )

    # --------------------------------------------------------
    # CREATE SCAN
    # --------------------------------------------------------

    scan = CVScan.objects.create(

        user=request.user,

        cv_filename=cv_file.name,

        cv_text=cv_text,

        job_description=job_description,

        status="processing",
    )

    # --------------------------------------------------------
    # RUN MATCHING
    # --------------------------------------------------------

    try:

        analysis = analyze_cv_against_job(
            cv_text,
            job_description
        )

        scan.match_score = analysis.get(
            "match_score"
        )

        scan.skill_score = analysis.get(
            "match_score"
        )

        scan.total_keywords = analysis.get(
            "counts",
            {}
        ).get(
            "all",
            0
        )

        scan.matched_keyword_count = analysis.get(
            "counts",
            {}
        ).get(
            "covered",
            0
        )

        scan.analysis = analysis

        # ----------------------------------------------------
        # BACKWARD COMPATIBILITY
        # ----------------------------------------------------

        scan.matched_keywords = [
            item["term"]
            for item in analysis.get(
                "terms",
                []
            )
            if item.get("status") == "COVERED"
        ]

        scan.missing_keywords = analysis.get(
            "missing_terms",
            []
        )

        scan.status = "completed"

        scan.error_message = ""

        scan.save()

        # ----------------------------------------------------
        # CONSUME FREE SCAN
        #
        # Paid users retain access without consuming their
        # free scan. Users without active paid access use
        # their free scan after successful analysis.
        # ----------------------------------------------------

        with transaction.atomic():

            subscription = UserSubscription.objects.select_for_update().get(
                user=request.user
            )

            if not subscription.has_paid_access():

                subscription.free_scan_used = True

                subscription.save(
                    update_fields=[
                        "free_scan_used"
                    ]
                )

        # ----------------------------------------------------
        # REDIRECT TO RESULT
        # ----------------------------------------------------

        return redirect(
            "scan_result",
            scan_id=scan.id
        )

    except Exception as exc:

        scan.status = "failed"

        scan.error_message = str(
            exc
        )

        scan.save()

        messages.error(
            request,
            f"Analysis failed: {exc}"
        )

        return redirect(
            "scan_cv"
        )


# ============================================================
# SCAN RESULT
# ============================================================

def scan_result(request, scan_id):

    if not request.user.is_authenticated:
        return redirect("account")

    scan = get_object_or_404(
        CVScan,
        id=scan_id,
        user=request.user,
    )

    return render(
        request,
        "core/scan_result.html",
        {
            "scan": scan,
        }
    )

# ============================================================
# SCAN RESULT
# ============================================================

def scan_result(request, scan_id):

    if not request.user.is_authenticated:
        return redirect("account")

    scan = get_object_or_404(
        CVScan,
        id=scan_id,
        user=request.user,
    )

    return render(
        request,
        "core/scan_result.html",
        {
            "scan": scan,
        }
    )


# ============================================================
# SCAN HISTORY
# ============================================================

def scan_history(request):

    if not request.user.is_authenticated:
        return redirect("account")

    scans = CVScan.objects.filter(
        user=request.user
    )

    return render(
        request,
        "core/scan_history.html",
        {
            "scans": scans,
        }
    )


# ============================================================
# RESCAN EXISTING CV
#
# This updates the EXISTING CVScan record.
#
# It does NOT create a new CVScan.
#
# It does NOT require a new CV upload.
# ============================================================

def rescan_scan(request, scan_id):

    # --------------------------------------------------------
    # AUTHENTICATION
    # --------------------------------------------------------

    if not request.user.is_authenticated:

        return redirect(
            "account"
        )


    # --------------------------------------------------------
    # GET EXISTING SCAN
    #
    # IMPORTANT:
    # Only allow the owner of the scan to edit it.
    # --------------------------------------------------------

    scan = get_object_or_404(
        CVScan,
        id=scan_id,
        user=request.user,
    )


    # --------------------------------------------------------
    # ONLY POST IS ALLOWED
    # --------------------------------------------------------

    if request.method != "POST":

        return redirect(
            "scan_result",
            scan_id=scan.id,
        )


    # --------------------------------------------------------
    # GET EDITED JOB DESCRIPTION
    #
    # If the field is not supplied, retain the existing JD.
    # --------------------------------------------------------

    submitted_job_description = (
        request.POST.get(
            "job_description",
            ""
        )
        .strip()
    )


    if submitted_job_description:

        new_job_description = (
            submitted_job_description
        )

    else:

        new_job_description = (
            scan.job_description
        )


    # --------------------------------------------------------
    # GET EDITED CV TEXT
    #
    # This is the important part.
    #
    # The user can edit the extracted CV directly in the
    # textarea. We use that text directly.
    #
    # NO FILE IS REQUIRED.
    # --------------------------------------------------------

    submitted_cv_text = (
        request.POST.get(
            "cv_text",
            ""
        )
        .strip()
    )


    # --------------------------------------------------------
    # OPTIONAL NEW FILE
    #
    # A user may still upload a completely different CV.
    # But this is OPTIONAL.
    #
    # Priority:
    #
    # 1. Uploaded file, if supplied
    # 2. Edited CV text
    # 3. Existing stored CV text
    # --------------------------------------------------------

    uploaded_cv = (
        request.FILES.get(
            "cv_file"
        )
    )


    try:

        # ====================================================
        # DETERMINE CV TEXT
        # ====================================================

        if uploaded_cv:

            # -----------------------------------------------
            # A genuinely new CV file was uploaded.
            # -----------------------------------------------

            new_cv_text = (
                extract_cv_text(
                    uploaded_cv
                )
            )

            new_cv_filename = (
                uploaded_cv.name
            )

        elif submitted_cv_text:

            # -----------------------------------------------
            # User edited the existing CV directly.
            #
            # No upload required.
            # -----------------------------------------------

            new_cv_text = (
                submitted_cv_text
            )

            # Keep the original filename as a reference.
            new_cv_filename = (
                scan.cv_filename
            )

        else:

            # -----------------------------------------------
            # Nothing was changed in the CV.
            #
            # Keep the existing CV.
            # -----------------------------------------------

            new_cv_text = (
                scan.cv_text
            )

            new_cv_filename = (
                scan.cv_filename
            )


        # ====================================================
        # VALIDATE CV
        # ====================================================

        if not new_cv_text:

            raise ValueError(
                "CV text is empty. Please edit your CV or upload a CV."
            )


        new_cv_text = (
            new_cv_text.strip()
        )


        # ====================================================
        # VALIDATE JOB DESCRIPTION
        # ====================================================

        if not new_job_description:

            raise ValueError(
                "Job description cannot be empty."
            )


        new_job_description = (
            new_job_description.strip()
        )


        # ====================================================
        # MARK AS PROCESSING
        # ====================================================

        scan.status = (
            "processing"
        )

        scan.error_message = ""

        scan.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ]
        )


        # ====================================================
        # RUN YOUR EXISTING MATCHING ENGINE
        #
        # We are NOT changing the matching engine here.
        # ====================================================

        analysis = (
            analyze_cv_against_job(
                new_cv_text,
                new_job_description,
            )
        )


        # ====================================================
        # UPDATE THE SAME DATABASE RECORD
        # ====================================================

        scan.cv_filename = (
            new_cv_filename
        )

        scan.cv_text = (
            new_cv_text
        )

        scan.job_description = (
            new_job_description
        )

        scan.match_score = (
            analysis.get(
                "match_score"
            )
        )


        # ----------------------------------------------------
        # BACKWARD-COMPATIBILITY FIELDS
        # ----------------------------------------------------

        scan.matched_keywords = [
            item.get(
                "term",
                ""
            )

            for item in analysis.get(
                "terms",
                []
            )

            if item.get(
                "status"
            ) == "COVERED"
        ]


        scan.missing_keywords = (
            analysis.get(
                "missing_terms",
                []
            )
        )


        scan.total_keywords = (
            analysis.get(
                "counts",
                {}
            ).get(
                "all",
                0
            )
        )


        scan.matched_keyword_count = (
            analysis.get(
                "counts",
                {}
            ).get(
                "covered",
                0
            )
        )


        # ----------------------------------------------------
        # SKILL COUNTS
        # ----------------------------------------------------

        hard_items = (
            analysis.get(
                "hard_skills",
                []
            )
        )

        soft_items = (
            analysis.get(
                "soft_skills",
                []
            )
        )


        scan.skill_score = (
            analysis.get(
                "scores",
                {}
            ).get(
                "hard",
                0
            )
        )


        scan.required_skill_count = (
            len(
                hard_items
            )
        )


        scan.matched_required_skill_count = sum(
            1
            for item in hard_items
            if item.get(
                "status"
            ) == "COVERED"
        )


        scan.preferred_skill_count = (
            len(
                soft_items
            )
        )


        scan.matched_preferred_skill_count = sum(
            1
            for item in soft_items
            if item.get(
                "status"
            ) == "COVERED"
        )


        # ----------------------------------------------------
        # SAVE COMPLETE ANALYSIS
        # ----------------------------------------------------

        scan.analysis = (
            analysis
        )

        scan.status = (
            "completed"
        )

        scan.error_message = ""


        # ====================================================
        # SAVE EVERYTHING
        #
        # This is the SAME scan record.
        # No new CVScan.objects.create()
        # ====================================================

        scan.save()


        # ====================================================
        # SUCCESS
        # ====================================================

        messages.success(
            request,
            "Your CV and job description were updated and rescanned successfully."
        )


        return redirect(
            "scan_result",
            scan_id=scan.id,
        )


    except Exception as exc:

        # ====================================================
        # ANALYSIS FAILED
        # ====================================================

        scan.status = (
            "failed"
        )

        scan.error_message = (
            str(exc)
        )

        scan.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ]
        )


        messages.error(
            request,
            f"Analysis failed: {exc}"
        )


        return redirect(
            "scan_result",
            scan_id=scan.id,
        )