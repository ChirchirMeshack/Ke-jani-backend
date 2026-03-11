"""
Signal architecture for apps/property_managers/:

FIRES:
  pm_assigned — after a property is successfully assigned to a PM.
  Listened by: apps/landlords/ (analytics, wizard)

LISTENS:
  tenant_created (from apps/tenants/) — if a PM manages the property,
  log to access_audit_log. Passive listener, no state change.
"""

from django.dispatch import Signal

# ── Outbound signal ──────────────────────────────────────────────────
# Fired by: accept_assignment() in services.py
# Payload: pm_instance, property_instance, assignment_request
pm_assigned = Signal()


def connect_external_signals():
    """
    Called from PropertyManagersConfig.ready().
    Connects listeners to signals from other apps.
    """
    try:
        from apps.tenants.signals import tenant_created
        tenant_created.connect(_on_tenant_created)
    except ImportError:
        pass


def _on_tenant_created(sender, tenant_instance, landlord, **kwargs):
    """
    When a tenant is created for a PM-managed property,
    log to audit trail so the PM can see the new tenant.
    """
    try:
        unit = tenant_instance.current_unit
        if not unit:
            return
        prop = unit.property
        if not prop.property_manager:
            return  # Self-managed — PM not involved
        from apps.users.models import AccessAuditLog
        AccessAuditLog.objects.create(
            user=prop.property_manager.user,
            event="invitation_sent",
            details={
                "type": "tenant_added_to_managed_property",
                "tenant_id":   tenant_instance.id,
                "property_id": prop.id,
                "unit_id":     unit.id,
            }
        )
    except Exception:
        pass  # Signal failures must never break tenant creation
