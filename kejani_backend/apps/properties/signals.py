"""
Two categories of signal code live here:

1. CUSTOM SIGNALS (property_created, unit_created, unit_status_changed)
   - Defined at the top of this file
   - Fired by services.py when business events occur
   - Listened by OTHER apps (landlords, listings, tenants)
   - apps/properties/ never knows who is listening — zero coupling

2. DJANGO MODEL SIGNALS (post_save on Property and Unit)
   - Maintain data integrity WITHIN the properties app
   - update_actual_units: keeps Property.actual_units accurate
   - create_default_penalty_rule: seeds a rule on every new Property
"""
import datetime
from decimal import Decimal

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import Signal, receiver


# ── Custom Signals ──────────────────────────────────────────────────
# Each Signal() call creates a new signal object.
# Other apps import these objects and use @receiver() to listen.

# Fired after a new Property is saved for the first time.
# Provides: property_instance, landlord (Landlord model instance)
property_created = Signal()

# Fired after a new Unit is saved for the first time.
# Provides: unit_instance, property_instance, landlord
unit_created = Signal()

# Fired whenever a Unit status column changes value.
# Provides: unit_instance, old_status, new_status
# Used by: listings app (auto-publish on vacant, deactivate on occupied)
unit_status_changed = Signal()


# ── Django Model Signal Handlers ────────────────────────────────────

@receiver(pre_save, sender="properties.Unit")
def capture_old_unit_status(sender, instance, **kwargs):
    """
    Captures the CURRENT status before the save happens.
    Stored as instance._old_status so post_save can compare.
    If this is a new unit (no pk yet), _old_status is None.
    """
    if instance.pk:
        try:
            instance._old_status = sender.objects.get(pk=instance.pk).status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender="properties.Unit")
def handle_unit_saved(sender, instance, created, **kwargs):
    """
    Fires after every Unit save. Does two things:
    1. Updates Property.actual_units count (always)
    2. Fires unit_status_changed signal if status changed (updates only)
    3. Fires unit_created custom signal (creates only)
    """
    from .models import Property

    # 1. Sync actual_units on the parent property
    active_count = (
        sender.objects
        .filter(property=instance.property, deleted_at__isnull=True)
        .count()
    )
    Property.objects.filter(pk=instance.property_id).update(actual_units=active_count)

    if created:
        # 3. Announce new unit to other apps
        unit_created.send(
            sender=sender,
            unit_instance=instance,
            property_instance=instance.property,
            landlord=instance.property.landlord,
        )
    else:
        # 2. Check if status changed and announce if so
        old = getattr(instance, "_old_status", None)
        if old and old != instance.status:
            unit_status_changed.send(
                sender=sender,
                unit_instance=instance,
                old_status=old,
                new_status=instance.status,
            )


@receiver(post_delete, sender="properties.Unit")
def handle_unit_deleted(sender, instance, **kwargs):
    """Updates actual_units when a unit is hard-deleted."""
    from .models import Property
    active_count = (
        sender.objects
        .filter(property=instance.property, deleted_at__isnull=True)
        .count()
    )
    Property.objects.filter(pk=instance.property_id).update(actual_units=active_count)


@receiver(post_save, sender="properties.Property")
def create_default_penalty_rule(sender, instance, created, **kwargs):
    """
    Seeds a default 5% penalty rule on every new Property.
    Schema maintenance checklist explicitly requires this.
    Grace period: 3 days. Effective immediately.
    Landlord can change it via PATCH /api/properties/<id>/penalty-rule/
    """
    if not created:
        return
    from .models import PenaltyRule
    PenaltyRule.objects.create(
        property=instance,
        penalty_type="percentage",
        penalty_value=Decimal("5.00"),
        grace_period_days=3,
        effective_from=datetime.date.today(),
    )
