from django.contrib import admin
from .models import UserSubscription, PaymentTransaction


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "status",
        "free_scan_used",
        "active_until",
    )

    list_filter = (
        "status",
        "free_scan_used",
    )

    search_fields = (
        "user__username",
        "user__email",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "reference",
        "amount",
        "currency",
        "status",
        "paid_at",
    )

    list_filter = (
        "status",
        "currency",
    )

    search_fields = (
        "user__username",
        "user__email",
        "reference",
    )

    readonly_fields = (
        "created_at",
    )