"""
apps/tenants/ listens for two signals from apps/properties/:

1. unit_status_changed — if a unit goes vacant, check if there is a tenant
   whose lease should be expired. (Defensive: the service layer already handles
   this, but this catches any manual unit status changes via admin.)

2. (Future) — apps/documents/ will fire a document_generated signal.
   apps/tenants/ will listen and update lease.lease_document_url.

apps/tenants/ also fires its own signal: tenant_created.
apps/landlords/ listens to advance wizard step 4.
"""

from django.dispatch import Signal


# ── Custom signal: fires after a tenant is fully created ─────────────
# Listened by: apps/landlords/ (advance wizard step 4)
tenant_created = Signal()


def _on_unit_status_changed(sender, unit_instance, old_status, new_status, **kwargs):
    """
    When a unit is manually set to vacant via admin or API,
    check if there is an active lease and expire it.
    This is a safety net — end_tenancy() in services.py is the primary path.
    """
    if new_status != "vacant":
        return
    try:
        from apps.leases.models import Lease
        active_lease = Lease.objects.filter(
            unit=unit_instance, status="active"
        ).first()
        if active_lease:
            active_lease.expire()
    except Exception:
        pass  # Never let a signal handler break a unit status update


def connect_property_signals():
    """
    Connects listeners for signals fired by apps/properties/.
    Called from apps/landlords/signals.py connect_property_signals()
    or can be called independently.
    """
    try:
        from apps.properties.signals import unit_status_changed
        unit_status_changed.connect(_on_unit_status_changed)
    except ImportError:
        pass  # properties app not yet installed — safe to ignore


# Auto-connect on module import (triggered by TenantsConfig.ready())
connect_property_signals()
