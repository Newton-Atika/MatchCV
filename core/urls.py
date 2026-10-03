from django.urls import path
from . import views


urlpatterns = [

    # ============================================================
    # LANDING
    # ============================================================

    path(
        "",
        views.landing_page,
        name="landing",
    ),


    path(
        "terms/",
        views.terms_of_use,
        name="terms_of_use"
    ),


    # ============================================================
    # ACCOUNT
    # ============================================================

    path(
        "account/",
        views.account,
        name="account",
    ),

    path(
        "account/register/",
        views.register,
        name="register",
    ),

    path(
        "account/dashboard/",
        views.account_dashboard,
        name="account_dashboard",
    ),


    # ============================================================
    # CV SCANNING
    # ============================================================

    path(
        "scan/",
        views.scan_cv,
        name="scan_cv",
    ),

    path(
        "scan/<int:scan_id>/",
        views.scan_result,
        name="scan_result",
    ),

    path(
        "scan/<int:scan_id>/rescan/",
        views.rescan_scan,
        name="rescan_scan",
    ),

    path(
        "scans/",
        views.scan_history,
        name="scan_history",
    ),

        path(
        "privacy/",
        views.privacy_policy,
        name="privacy_policy"
    ),

    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path(
        "payments/callback/",
        views.payment_callback,
        name="payment_callback"
    ),

    path(
        "payments/webhook/",
        views.paystack_webhook,
        name="paystack_webhook"
    ),

        path(
        "subscription/",
        views.subscription,
        name="subscription"
    ),

    path(
        "payments/card/",
        views.initialize_card_payment,
        name="initialize_card_payment"
    ),

    path(
        "payments/mpesa/",
        views.initialize_mpesa_payment,
        name="initialize_mpesa_payment"
    ),

    path(
        "payments/callback/",
        views.payment_callback,
        name="payment_callback"
    ),

    path(
        "payments/status/<str:reference>/",
        views.check_payment_status,
        name="check_payment_status"
    ),

    path(
        "payments/paystack-webhook/",
        views.paystack_webhook,
        name="paystack_webhook"
    ),
]