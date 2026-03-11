from django.db import models
from django.utils import timezone


LEASE_STATUS_CHOICES = [
    ('active',      'Active'),
    ('expired',     'Expired — end date passed, not renewed'),
    ('terminated',  'Terminated — ended early by mutual agreement'),
    ('pending',     'Pending — signed but not yet started'),
]


class Lease(models.Model):
    """
    The financial contract between a landlord and a tenant for a unit.

    A tenant may have multiple Lease rows over time (renewals create new rows).
    The CURRENT lease is: Lease.objects.filter(tenant=t, status="active").first()

    Lease is NEVER soft-deleted. Termination = status="terminated".
    This preserves the financial history required by Kenyan law.

    lease_document_url is nullable — populated by apps/documents/ when built.
    Until then it remains None and the tenant sees "Document pending".
    """

    # ── Parties ───────────────────────────────────────────────────
    # Forward-reference strings avoid circular import at module load time.
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.PROTECT,
        # PROTECT not CASCADE — never delete a lease because a tenant was removed.
        # Terminate the lease first, then handle the tenant record.
        related_name='leases',
        db_index=True,
    )
    unit = models.ForeignKey(
        'properties.Unit',
        on_delete=models.PROTECT,
        related_name='leases',
        db_index=True,
    )

    # ── Terms ─────────────────────────────────────────────────────
    lease_start    = models.DateField()
    lease_end      = models.DateField()
    monthly_rent   = models.DecimalField(max_digits=12, decimal_places=2)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2)
    # rent_due_day: 1–28 (avoid 29/30/31 — not all months have them)
    rent_due_day   = models.IntegerField(default=1)
    grace_period_days = models.IntegerField(
        default=3,
        help_text="Days after rent_due_day before late penalty kicks in.",
    )

    # ── Status ────────────────────────────────────────────────────
    status = models.CharField(
        max_length=15,
        choices=LEASE_STATUS_CHOICES,
        default="active",
        db_index=True,
    )

    # ── Signatures & document ─────────────────────────────────────
    # tenant_signed_at: set when tenant views + accepts lease on first login
    tenant_signed_at   = models.DateTimeField(null=True, blank=True)
    # lease_document_url: populated by apps/documents/ when it is built.
    # Until then, this is None. Frontend shows "Document being prepared."
    lease_document_url = models.URLField(
        blank=True,
        help_text="Cloudinary URL of the generated lease PDF. Set by apps/documents/.",
    )

    # ── Renewal tracking ──────────────────────────────────────────
    # If this lease was created as a renewal, previous_lease points to the old one.
    # Allows full lease history: tenant.leases.all() shows every term.
    previous_lease = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="renewals",
        help_text="The lease this one replaced (for renewals).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'leases'
        verbose_name = 'Lease'
        verbose_name_plural = 'Leases'
        ordering = ['-lease_start']

    def __str__(self):
        return f"Lease: {self.tenant} | {self.unit} | {self.lease_start} → {self.lease_end}"

    @property
    def is_active(self):
        return self.status == "active"

    @property
    def days_remaining(self):
        """Days until lease_end. Negative = already expired."""
        return (self.lease_end - timezone.localdate()).days

    @property
    def is_expiring_soon(self):
        """True if lease ends within 30 days — used for renewal reminders."""
        return 0 <= self.days_remaining <= 30

    def terminate(self, reason=""):
        """Ends a lease early. Does NOT change the unit status — caller must do that."""
        self.status = "terminated"
        self.save(update_fields=["status", "updated_at"])

    def expire(self):
        """Called by Celery task when lease_end date passes."""
        self.status = "expired"
        self.save(update_fields=["status", "updated_at"])
