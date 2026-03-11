from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

PAYMENT_PREFERENCE_CHOICES = [
    ('mpesa', 'M-Pesa STK Push'),
    ('bank',  'Bank Transfer'),
]

NOTIFICATION_PREFERENCE_CHOICES = [
    ('sms',       'SMS Only'),
    ('email',     'Email Only'),
    ('sms_email', 'SMS and Email'),
]


class ActiveTenantManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Tenant(models.Model):
    """
    Profile layer for tenant-specific data.
    Sits on top of apps.users.User (one-to-one).

    A tenant is always linked to a Unit at creation.
    If they move units, the Lease changes — the Tenant profile stays.

    Access patterns:
      From a User:    request.user.tenant_profile
      From a Tenant:  tenant.user
      Current lease:  tenant.current_lease  (queries DB — use prefetch in views)
      Current unit:   tenant.current_unit   (via current_lease)
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='tenant_profile',
        db_index=True,
    )

    # ── Identity ──────────────────────────────────────────────────
    id_number = models.CharField(
        max_length=20, blank=True,
        help_text="National ID number.",
    )
    # phone_alt: collected at creation, stored here.
    # Primary phone is on users.phone.
    phone_alt = models.CharField(
        max_length=15, blank=True,
        help_text="Alternative contact number.",
    )

    # ── Documents (Cloudinary URLs) ────────────────────────────────
    id_copy_front_url = models.URLField(blank=True)
    id_copy_back_url  = models.URLField(blank=True)

    # ── Emergency contact ─────────────────────────────────────────
    emergency_contact_name         = models.CharField(max_length=200, blank=True)
    emergency_contact_phone        = models.CharField(max_length=15,  blank=True)
    emergency_contact_relationship = models.CharField(max_length=100, blank=True)

    # ── Employment (optional, for reference) ──────────────────────
    employer_name    = models.CharField(max_length=200, blank=True)
    employer_contact = models.CharField(max_length=100, blank=True)

    # ── Preferences ───────────────────────────────────────────────
    payment_preference = models.CharField(
        max_length=10,
        choices=PAYMENT_PREFERENCE_CHOICES,
        default='mpesa',
    )
    notification_preference = models.CharField(
        max_length=10,
        choices=NOTIFICATION_PREFERENCE_CHOICES,
        default='sms',
        help_text="How the tenant prefers to receive reminders.",
    )

    # ── KDPA compliance ───────────────────────────────────────────
    terms_accepted_at = models.DateTimeField(null=True, blank=True)

    # ── Onboarding state ──────────────────────────────────────────
    # True after tenant changes their temp password on first login
    has_changed_password = models.BooleanField(default=False)
    # True after tenant views the lease agreement on first login
    has_viewed_lease     = models.BooleanField(default=False)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    # ── Soft delete ───────────────────────────────────────────────
    # NOTE: Always terminate the active Lease FIRST, then soft-delete Tenant.
    # services.end_tenancy() handles this in the correct order.
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects     = ActiveTenantManager()
    objects_all = models.Manager()

    class Meta:
        db_table = 'tenants'
        verbose_name = 'Tenant'
        verbose_name_plural = 'Tenants'

    def __str__(self):
        return f"{self.user.full_name} (Tenant)"

    @property
    def current_lease(self):
        """
        Returns the active Lease for this tenant, or None.
        Warning: this hits the DB. Use prefetch_related("leases") in list views.
        """
        return self.leases.filter(status="active").first()

    @property
    def current_unit(self):
        """Returns the unit the tenant currently occupies, or None."""
        lease = self.current_lease
        return lease.unit if lease else None

    @property
    def is_onboarding_complete(self):
        return self.onboarding_completed_at is not None

    def complete_onboarding(self):
        """Marks tenant onboarding done when both steps are complete."""
        if self.has_changed_password and self.has_viewed_lease:
            if not self.onboarding_completed_at:
                self.onboarding_completed_at = timezone.now()
                self.save(update_fields=["onboarding_completed_at"])

    def soft_delete(self):
        """
        Soft-deletes this tenant record.
        IMPORTANT: Call services.end_tenancy() instead of this directly.
        end_tenancy() terminates the lease and updates the unit status first.
        """
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])
