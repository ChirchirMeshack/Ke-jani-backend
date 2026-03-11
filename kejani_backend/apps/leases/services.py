import datetime
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from .models import Lease


def get_lease_or_404(lease_id, tenant=None):
    """
    Returns a Lease by ID. If tenant is given, also verifies ownership.
    Raises NotFound (HTTP 404) if not found or not owned.
    """
    qs = Lease.objects.select_related("tenant__user", "unit__property")
    try:
        lease = qs.get(pk=lease_id)
    except Lease.DoesNotExist:
        raise NotFound("Lease not found.")
    if tenant and lease.tenant != tenant:
        raise NotFound("Lease not found.")
    return lease


def get_active_lease(tenant):
    """
    Returns the active lease for a tenant, or None.
    A tenant should always have at most one active lease.
    """
    return Lease.objects.filter(tenant=tenant, status="active").first()


@transaction.atomic
def create_lease(tenant, unit, validated_data):
    """
    Creates a new Lease row.
    Called by apps/tenants/services.py create_tenant() — not called directly by views.

    lease_document_url is intentionally not set here.
    apps/documents/ will populate it when built.

    :returns: the created Lease instance
    """
    return Lease.objects.create(
        tenant=tenant,
        unit=unit,
        lease_start=validated_data["lease_start"],
        lease_end=validated_data["lease_end"],
        monthly_rent=validated_data["monthly_rent"],
        deposit_amount=validated_data["deposit_amount"],
        rent_due_day=validated_data.get("rent_due_day", 1),
        grace_period_days=validated_data.get("grace_period_days", 3),
    )


@transaction.atomic
def update_lease(lease, validated_data):
    """
    Updates allowed lease fields.
    Cannot change tenant or unit — those are structural.
    :returns: updated Lease instance
    """
    allowed = [
        "lease_end", "monthly_rent", "deposit_amount",
        "rent_due_day", "grace_period_days",
    ]
    for field in allowed:
        if field in validated_data:
            setattr(lease, field, validated_data[field])
    lease.save()
    return lease


@transaction.atomic
def renew_lease(old_lease, new_end_date, new_monthly_rent=None):
    """
    Creates a new Lease as a renewal of the current one.
    The old lease is set to "expired". The new lease starts the day after.

    :param old_lease: the Lease being renewed
    :param new_end_date: the end date of the new lease term
    :param new_monthly_rent: optional new rent amount (defaults to current)
    :returns: the new Lease instance
    """
    old_lease.expire()

    new_lease = Lease.objects.create(
        tenant=old_lease.tenant,
        unit=old_lease.unit,
        lease_start=old_lease.lease_end + datetime.timedelta(days=1),
        lease_end=new_end_date,
        monthly_rent=new_monthly_rent or old_lease.monthly_rent,
        deposit_amount=old_lease.deposit_amount,
        rent_due_day=old_lease.rent_due_day,
        grace_period_days=old_lease.grace_period_days,
        previous_lease=old_lease,
    )
    return new_lease


def get_expiring_leases(landlord, days=30):
    """
    Returns active leases expiring within `days` days for a landlord.
    Used by the dashboard renewal reminders widget.
    :returns: QuerySet of Lease objects
    """
    today    = timezone.localdate()
    deadline = today + datetime.timedelta(days=days)
    return (
        Lease.objects
        .filter(
            unit__property__landlord=landlord,
            status="active",
            lease_end__range=(today, deadline),
        )
        .select_related("tenant__user", "unit__property")
        .order_by("lease_end")
    )
