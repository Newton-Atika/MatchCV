from django.contrib.auth.models import User
from django.db import models



from django.conf import settings
from django.db import models
from django.utils import timezone


class UserSubscription(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription"
    )

    free_scan_used = models.BooleanField(default=False)

    status = models.CharField(
        max_length=200,
        choices=[
            ("inactive", "Inactive"),
            ("active", "Active"),
            ("expired", "Expired"),
        ],
        default="inactive"
    )

    active_until = models.DateTimeField(null=True, blank=True)

    last_payment_reference = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def has_paid_access(self):
        return (
            self.active_until is not None
            and self.active_until > timezone.now()
        )

    def can_scan(self):
        return self.has_paid_access() or not self.free_scan_used

    def update_status(self):
        if self.has_paid_access():
            self.status = "active"
        elif self.active_until:
            self.status = "expired"
        else:
            self.status = "inactive"

        self.save(update_fields=["status", "updated_at"])

    def days_remaining(self):
        if not self.has_paid_access():
            return 0

        remaining = self.active_until - timezone.now()
        return max(0, remaining.days + (1 if remaining.seconds else 0))

    def __str__(self):
        return f"{self.user} - {self.status}"


class PaymentTransaction(models.Model):
    PAYMENT_METHODS = [
        ("mpesa", "M-Pesa"),
        ("card", "Visa/Card"),
    ]

    PAYMENT_STATUSES = [
        ("pending", "Pending"),
        ("success", "Successful"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payment_transactions"
    )

    reference = models.CharField(
        max_length=100,
        unique=True
    )

    amount = models.PositiveIntegerField(default=20000)
    currency = models.CharField(max_length=5, default="KES")

    payment_method = models.CharField(
        max_length=200,
        choices=PAYMENT_METHODS,

        default=""
    )

    status = models.CharField(
        max_length=200,
        choices=PAYMENT_STATUSES,
        default="pending"
    )

    gateway_message = models.TextField(blank=True)
    phone_number = models.CharField(max_length=200, blank=True)

    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.reference} - {self.status}"


class Profile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    phone = models.CharField(
        max_length=30,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.user.email or self.user.username


class Skill(models.Model):
    """
    Local copy of the skills vocabulary.

    Primarily populated from ESCO.
    We also support a small built-in fallback vocabulary.
    """

    SOURCE_CHOICES = [
        ("esco", "ESCO"),
        ("builtin", "Built-in"),
        ("custom", "Custom"),
    ]

    concept_uri = models.CharField(
        max_length=500,
        unique=True,
        null=True,
        blank=True
    )

    preferred_label = models.CharField(
        max_length=500,
        db_index=True
    )

    alt_labels = models.JSONField(
        default=list,
        blank=True
    )

    description = models.TextField(
        blank=True
    )

    skill_type = models.CharField(
        max_length=100,
        blank=True
    )

    source = models.CharField(
        max_length=200,
        choices=SOURCE_CHOICES,
        default="esco"
    )

    active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.preferred_label

    class Meta:
        ordering = ["preferred_label"]


class CVScan(models.Model):

    STATUS_CHOICES = [
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="cv_scans"
    )

    # We deliberately DO NOT store the uploaded CV file.
    cv_filename = models.CharField(
        max_length=255
    )

    cv_text = models.TextField()

    job_description = models.TextField()

    # Main score
    match_score = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    # Backwards-compatible fields
    matched_keywords = models.JSONField(
        default=list,
        blank=True
    )

    missing_keywords = models.JSONField(
        default=list,
        blank=True
    )

    total_keywords = models.PositiveIntegerField(
        default=0
    )

    matched_keyword_count = models.PositiveIntegerField(
        default=0
    )

    # New structured matching information
    skill_score = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    required_skill_count = models.PositiveIntegerField(
        default=0
    )

    matched_required_skill_count = models.PositiveIntegerField(
        default=0
    )

    preferred_skill_count = models.PositiveIntegerField(
        default=0
    )

    matched_preferred_skill_count = models.PositiveIntegerField(
        default=0
    )

    # Complete analysis result
    analysis = models.JSONField(
        default=dict,
        blank=True
    )

    status = models.CharField(
        max_length=200,
        choices=STATUS_CHOICES,
        default="processing"
    )

    error_message = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.cv_filename}"

    @property
    def score_label(self):
        if self.match_score is None:
            return "Not scored"

        if self.match_score >= 85:
            return "Excellent Match"

        if self.match_score >= 75:
            return "Strong Match"

        if self.match_score >= 60:
            return "Good Match"

        if self.match_score >= 45:
            return "Moderate Match"

        return "Low Match"