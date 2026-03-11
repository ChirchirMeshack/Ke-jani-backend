import builtins

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

# ── PM Subscription Tiers ─────────────────────────────────────────────
# Left here as choices for the synced CharField
PM_SUBSCRIPTION_TIERS = [
    ('starter_pm',      'Starter PM — up to 50 units, Ksh 3,000/mo'),
    ('professional_pm', 'Professional PM — up to 150 units, Ksh 6,000/mo'),
    ('enterprise_pm',   'Enterprise PM — custom pricing'),
]


# ── Approval status ───────────────────────────────────────────────────
PM_APPROVAL_STATUS = [
    ('pending',   'Pending Approval'),
    ('approved',  'Approved'),
    ('rejected',  'Rejected'),
    ('suspended', 'Suspended'),
]

# ── Assignment request status ─────────────────────────────────────────
ASSIGNMENT_STATUS = [
    ('pending',   'Pending — awaiting PM response'),
    ('accepted',  'Accepted — PM managing property'),
    ('declined',  'Declined — PM said no'),
    ('cancelled', 'Cancelled — landlord withdrew request'),
    ('expired',   'Expired — PM did not respond in time'),
]

# ── Commission record status ──────────────────────────────────────────
COMMISSION_STATUS = [
    ('pending',   'Pending — rent collected, commission not yet paid'),
    ('paid',      'Paid — landlord has transferred commission to PM'),
    ('disputed',  'Disputed — under review'),
    ('waived',    'Waived — landlord waived this commission'),
]

# ── Kenyan counties (reuse from apps/properties/models.py) ──────
from apps.properties.models import KENYA_COUNTIES


# ── Managers ──────────────────────────────────────────────────────────

class ActivePMManager(models.Manager):
    """Default manager — filters out soft-deleted records."""
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


# ══════════════════════════════════════════════════════════════════════
#  PropertyManager
# ══════════════════════════════════════════════════════════════════════

class PropertyManager(models.Model):
    """
    Profile layer for property manager-specific data.
    Sits on top of apps.users.User (OneToOne).

    Access patterns:
      From a User:    request.user.pm_profile
      From a PM:      pm.user
      Managed props:  pm.managed_properties.all()  (reverse FK on Property)

    Approval mirrors Landlord:
      pending → approved (admin) → can accept assignments
      pending → rejected (admin) → cannot log in to features
      approved → suspended (admin) → loses access immediately
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='pm_profile',
        db_index=True,
    )

    # ── Identity ──────────────────────────────────────────────────
    id_number = models.CharField(
        max_length=20, blank=True,
        help_text="National ID number. Required before admin approval.",
    )
    company_name = models.CharField(
        max_length=200, blank=True,
        help_text="Optional company or agency name.",
    )

    # ── Profile (shown to landlords in PM search directory) ───────
    bio = models.TextField(
        blank=True,
        help_text="Short bio shown to landlords when they search for PMs.",
    )
    is_searchable = models.BooleanField(
        default=False,
        help_text="Controls PM visibility in landlord search. True when onboarding complete.",
    )

    # ── Documents (Cloudinary URLs) ────────────────────────────────
    id_copy_front_url = models.URLField(blank=True)
    id_copy_back_url  = models.URLField(blank=True)

    # ── Commission (default rate — overridden per property) ────────
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=10.00,
        help_text="Default commission % (e.g. 10.00 = 10%). Negotiated per property.",
    )

    # ── Subscription ──────────────────────────────────────────────
    subscription_tier = models.CharField(
        max_length=20,
        choices=PM_SUBSCRIPTION_TIERS,
        default='starter_pm',
    )
    subscription_active = models.BooleanField(default=False)

    # ── Approval ──────────────────────────────────────────────────
    approval_status = models.CharField(
        max_length=20,
        choices=PM_APPROVAL_STATUS,
        default='pending',
        db_index=True,
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='pm_approvals',
        help_text="Admin user who approved or rejected this PM.",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(
        blank=True,
        help_text="Required if approval_status=rejected.",
    )

    # ── Onboarding steps ──────────────────────────────────────────
    onboarding_step_profile_completed      = models.BooleanField(default=False)
    onboarding_step_subscription_completed = models.BooleanField(default=False)
    onboarding_step_banking_completed      = models.BooleanField(default=False)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    # ── Soft delete ───────────────────────────────────────────────
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects     = ActivePMManager()
    objects_all = models.Manager()

    class Meta:
        db_table = 'property_managers'
        verbose_name = 'Property Manager'
        verbose_name_plural = 'Property Managers'

    def __str__(self):
        return f"{self.user.full_name} (PM)"

    # ── Computed properties ────────────────────────────────────────
    @builtins.property
    def is_approved(self):
        return self.approval_status == "approved"

    @builtins.property
    def total_units_managed(self):
        """Total live units across all actively managed properties."""
        return sum(
            p.actual_units
            for p in self.managed_properties.filter(deleted_at__isnull=True)
        )

    @builtins.property
    def is_onboarding_complete(self):
        return self.onboarding_completed_at is not None

    @builtins.property
    def onboarding_progress(self):
        """Returns a dict used by the frontend onboarding wizard."""
        steps = {
            'profile':      self.onboarding_step_profile_completed,
            'subscription': self.onboarding_step_subscription_completed,
            'banking':      self.onboarding_step_banking_completed,
        }
        completed = sum(1 for v in steps.values() if v)
        total     = len(steps)
        percent   = int((completed / total) * 100)

        current_step = "completed"
        for step_name, done in steps.items():
            if not done:
                current_step = step_name
                break

        return {
            **steps,
            "current_step":     current_step,
            "percent_complete": percent,
            "is_complete":      self.is_onboarding_complete,
        }

    # ── Onboarding step completion ─────────────────────────────────
    ONBOARDING_STEPS = ("profile", "subscription", "banking")

    def complete_step(self, step_name):
        """
        Marks an onboarding step as complete. Idempotent.
        Auto-marks onboarding_completed_at when all steps are done.
        """
        if step_name not in self.ONBOARDING_STEPS:
            raise ValueError(
                f"Unknown PM onboarding step: {step_name!r}. "
                f"Valid steps: {self.ONBOARDING_STEPS}"
            )
        field = f"onboarding_step_{step_name}_completed"
        if not getattr(self, field):
            setattr(self, field, True)
            self.save(update_fields=[field, "updated_at"])
        self._mark_onboarding_complete()

    def _mark_onboarding_complete(self):
        """Checks if all steps done and marks onboarding complete."""
        all_done = all(
            getattr(self, f"onboarding_step_{s}_completed")
            for s in self.ONBOARDING_STEPS
        )
        if all_done and not self.onboarding_completed_at:
            self.onboarding_completed_at = timezone.now()
            self.is_searchable = True
            self.save(update_fields=["onboarding_completed_at", "is_searchable", "updated_at"])

    def soft_delete(self):
        """Soft-deletes this PM record. Does NOT delete User."""
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])


# ══════════════════════════════════════════════════════════════════════
#  PmServiceArea
# ══════════════════════════════════════════════════════════════════════

class PmServiceArea(models.Model):
    """
    Stores the counties and areas where a PM operates.
    Used in GET /api/property-managers/search/?county=nairobi
    """

    pm = models.ForeignKey(
        PropertyManager,
        on_delete=models.CASCADE,
        related_name='service_areas',
        db_index=True,
    )
    county = models.CharField(
        max_length=50,
        choices=KENYA_COUNTIES,
        help_text="One of the 47 Kenyan counties.",
    )
    area = models.CharField(
        max_length=100, blank=True,
        help_text="Specific area within the county. Blank = entire county.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pm_service_areas'
        verbose_name = 'PM Service Area'
        verbose_name_plural = 'PM Service Areas'
        unique_together = [('pm', 'county', 'area')]
        ordering = ['county', 'area']

    def __str__(self):
        loc = f"{self.county}, {self.area}" if self.area else self.county
        return f"{self.pm.user.full_name} — {loc}"


# ══════════════════════════════════════════════════════════════════════
#  PmAssignmentRequest
# ══════════════════════════════════════════════════════════════════════

class PmAssignmentRequest(models.Model):
    """
    Tracks a landlord's request for a PM to manage a property.

    Lifecycle:
      pending   → PM notified, waiting for response
      accepted  → Property.management_mode = "delegated", Property.property_manager = pm
      declined  → Property stays self-managed
      cancelled → Landlord withdrew before PM responded
      expired   → PM did not respond within 7 days (Celery task)

    For token-based invites (new PM, no account yet):
      - pm is NULL until the PM creates their account
      - invite_email + invite_token track the outstanding invite
      - invite_token_expires_at set to 7 days from creation
      - When PM registers via token: pm gets set, status → accepted
    """

    # ── Parties ───────────────────────────────────────────────────
    landlord = models.ForeignKey(
        'landlords.Landlord',
        on_delete=models.CASCADE,
        related_name='pm_assignment_requests',
        db_index=True,
    )
    pm = models.ForeignKey(
        PropertyManager,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assignment_requests',
        db_index=True,
    )
    property = models.ForeignKey(
        'properties.Property',
        on_delete=models.CASCADE,
        related_name='pm_assignment_requests',
        db_index=True,
    )

    # ── Terms negotiated during request ───────────────────────────
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Agreed commission rate for this property (%).",
    )
    can_add_tenants        = models.BooleanField(default=True)
    can_handle_maintenance = models.BooleanField(default=True)
    expense_approval_threshold = models.DecimalField(
        max_digits=10, decimal_places=2, default=10000,
        help_text="PM must get landlord approval for expenses above this amount.",
    )
    proposed_start_date = models.DateField(null=True, blank=True)

    # ── Status ────────────────────────────────────────────────────
    status = models.CharField(
        max_length=15,
        choices=ASSIGNMENT_STATUS,
        default='pending',
        db_index=True,
    )
    decline_reason = models.TextField(
        blank=True,
        help_text="Reason provided by PM when declining.",
    )

    # ── Token-based invite fields ─────────────────────────────────
    invite_email = models.EmailField(blank=True)
    invite_name  = models.CharField(max_length=200, blank=True)
    invite_phone = models.CharField(max_length=15, blank=True)
    invite_token = models.CharField(
        max_length=64, blank=True, db_index=True,
        help_text="Secure random token. Blank for existing-PM assignments.",
    )
    invite_token_expires_at = models.DateTimeField(null=True, blank=True)

    # ── Timestamps ────────────────────────────────────────────────
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pm_assignment_requests'
        verbose_name = 'PM Assignment Request'
        verbose_name_plural = 'PM Assignment Requests'
        ordering = ['-created_at']

    def __str__(self):
        pm_name = self.pm.user.full_name if self.pm else self.invite_name or self.invite_email
        return f"{self.property} → {pm_name} [{self.status}]"

    @builtins.property
    def is_invite_token_valid(self):
        """True if the invite token exists and has not expired."""
        if not self.invite_token or not self.invite_token_expires_at:
            return False
        return timezone.now() < self.invite_token_expires_at


# ══════════════════════════════════════════════════════════════════════
#  CommissionRecord
# ══════════════════════════════════════════════════════════════════════

class CommissionRecord(models.Model):
    """
    Records the commission owed to a PM for a specific rent collection.

    One CommissionRecord is created per Payment (rent collection).
    apps/payments/ creates the Payment row and links it back here.

    payment_id is a nullable IntegerField — apps/payments/ will fill it
    when the Payment model is built. Same stub pattern as lease_document_url.
    """

    pm = models.ForeignKey(
        PropertyManager,
        on_delete=models.PROTECT,
        related_name='commission_records',
        db_index=True,
    )
    property = models.ForeignKey(
        'properties.Property',
        on_delete=models.PROTECT,
        related_name='commission_records',
        db_index=True,
    )
    # payment FK stub — will become a real FK when apps/payments/ is built.
    # For now, storing as nullable integer to avoid missing-app migration errors.
    payment_id = models.IntegerField(
        null=True, blank=True,
        help_text="FK to payments.Payment. Stub until apps/payments/ is built.",
    )

    # ── Financials ────────────────────────────────────────────────
    rent_amount       = models.DecimalField(max_digits=12, decimal_places=2)
    commission_rate   = models.DecimalField(max_digits=5,  decimal_places=2)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2)
    period            = models.CharField(
        max_length=7,
        help_text="YYYY-MM format — which month this commission is for.",
    )

    # ── Status ────────────────────────────────────────────────────
    status = models.CharField(
        max_length=10,
        choices=COMMISSION_STATUS,
        default='pending',
        db_index=True,
    )
    paid_at       = models.DateTimeField(null=True, blank=True)
    payment_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'commission_records'
        verbose_name = 'Commission Record'
        verbose_name_plural = 'Commission Records'
        ordering = ['-created_at']

    def __str__(self):
        return f"Commission: {self.pm} | {self.property} | {self.period} | Ksh {self.commission_amount}"

    @classmethod
    def calculate_commission(cls, rent_amount, commission_rate):
        """
        Utility: calculates commission_amount from rent and rate.
        Example: calculate_commission(Decimal("25000"), Decimal("10.00")) → Decimal("2500.00")
        """
        from decimal import Decimal, ROUND_HALF_UP
        return (rent_amount * commission_rate / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
