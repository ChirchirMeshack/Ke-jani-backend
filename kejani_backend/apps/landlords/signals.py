"""
Landlord profile auto-creation signal.

WHY THIS EXISTS:
The auth app (apps/users/) handles registration and approval.
It knows nothing about the Landlord model — and it should stay that way.
When an admin approves a landlord, they set user.approval_status = 'approved'.
This signal watches for that change and creates the Landlord profile row.

HOW THE TEMP ATTRIBUTES WORK:
During registration, the auth view temporarily sets attributes on the User
instance before saving it:
  user._id_number = '12345678'
  user._estimated_properties = '11-30'
  user.save()

The post_save signal receives the same in-memory `instance` object.
So `instance._id_number` is available AT THIS MOMENT — but only on this
signal call. If the admin approves the user later (a separate save()),
these attrs are gone. Given our update to store id_number directly on User,
we can fall back to the instance.id_number if _id_number isn't present.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from apps.users.emails import send_approval_email

User = get_user_model()


@receiver(post_save, sender=User)
def create_landlord_profile_on_approval(sender, instance, created, **kwargs):
    """
    Fires on every User save. Creates a Landlord profile when:
    1. user.role == 'landlord'
    2. user.approval_status == 'approved'
    3. No Landlord profile exists yet for this user
    """
    if instance.role != 'landlord':
        return
    if instance.approval_status != 'approved':
        return

    from .services import create_landlord_profile  # local import avoids circular

    # Fallback to instance.id_number since we added it to USer
    id_number = getattr(instance, '_id_number', instance.id_number)
    estimated_units_range = getattr(instance, '_estimated_properties', '')

    landlord, created_now = create_landlord_profile(
        user=instance,
        id_number=id_number,
        estimated_units_range=estimated_units_range,
    )

    if created_now:
        # Log to audit trail — wrapped in try/except so audit failure
        # never breaks profile creation
        try:
            from apps.users.models import AccessAuditLog
            AccessAuditLog.objects.create(
                user=instance,
                event='account_approved',
                metadata={'landlord_id': landlord.id},
            )
        except Exception:
            pass  # Audit log failure must NEVER break profile creation

        # Send welcome email notification
        try:
            send_approval_email(instance)
        except Exception:
            pass

# ── Listen to properties app signals ────────────────────────────────
# These handlers advance the onboarding wizard when a landlord adds
# their first property (step 2) and first unit (step 3).
# Imported lazily to avoid circular imports at module load time.

def _get_property_created_signal():
    from apps.properties.signals import property_created
    return property_created

def _get_unit_created_signal():
    from apps.properties.signals import unit_created
    return unit_created


def on_property_created(sender, property_instance, landlord, **kwargs):
    """Advance wizard Step 2 when landlord creates their first property."""
    try:
        landlord.complete_step("property")
    except Exception:
        pass  # Wizard step failure must never break property creation


def on_unit_created(sender, unit_instance, property_instance, landlord, **kwargs):
    """Advance wizard Step 3 when landlord creates their first unit."""
    try:
        landlord.complete_step("units")
    except Exception:
        pass


def connect_property_signals():
    """
    Called from LandlordsConfig.ready() to wire up signal listeners.
    Using a function instead of @receiver avoids import-time circular deps.
    """
    _get_property_created_signal().connect(on_property_created)
    _get_unit_created_signal().connect(on_unit_created)
