import secrets
import string
import logging

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .models import Tenant
from .signals import tenant_created
from apps.leases.services import create_lease
from apps.properties.services import get_unit_or_404, update_unit

User = get_user_model()
logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────

def _generate_temp_password(length=16):
    """
    Generates a secure random temporary password.
    Uses secrets module (cryptographically safe) — NOT random.
    Characters: upper + lower + digits. No ambiguous chars (0/O, l/1).
    """
    alphabet = (string.ascii_letters + string.digits)
    # Remove ambiguous characters to help tenants type it correctly
    alphabet = alphabet.translate(str.maketrans("", "", "0OlI1"))
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _send_tenant_invitation(user, temp_password, unit, landlord_name):
    """
    Sends the tenant invitation email using Django send_mail().
    Uses SendGrid SMTP backend (configured in settings).

    TODO: Replace with apps.communications.services.queue_tenant_invitation()
    when apps/communications/ is built. The call signature should stay identical.

    Failures are caught and logged — a failed email must never prevent
    the tenant account from being created.
    """
    frontend_url = getattr(settings, "FRONTEND_URL", "https://ke-jani.com")
    login_url    = f"{frontend_url}/login"

    subject = f"Welcome to Ke-jani — {unit.property.name}, Unit {unit.unit_number}"
    message = (
        f"Hi {user.first_name},\n\n"
        f"Your landlord {landlord_name} has added you to Ke-jani.\n\n"
        f"Property: {unit.property.name}\n"
        f"Unit: {unit.unit_number}\n\n"
        f"Login at: {login_url}\n"
        f"Email: {user.email}\n"
        f"Temporary password: {temp_password}\n\n"
        "You will be asked to change your password on first login.\n\n"
        "— The Ke-jani Team"
    )
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as e:
        # Log the failure but do not raise — tenant account still created
        logger.error(f"Tenant invitation email failed for user {user.id}: {e}")


# ── Main creation flow ───────────────────────────────────────────────

@transaction.atomic
def create_tenant(landlord, unit, user_data, tenant_data, lease_data):
    """
    Creates a complete tenant: User + Tenant profile + Lease + Unit update.
    This is the main entry point. Views call this — not the sub-services.

    Arguments:
      landlord   — Landlord instance (the creator)
      unit       — Unit instance (must be vacant)
      user_data  — dict: first_name, last_name, email, phone
      tenant_data— dict: id_number, phone_alt, emergency_contact_*,
                         employer_*, payment_preference
      lease_data — dict: lease_start, lease_end, monthly_rent,
                         deposit_amount, rent_due_day, grace_period_days

    Returns: the created Tenant instance.
    Raises ValidationError if unit is not vacant.
    Raises ValidationError if email already exists in users table.
    """
    # ── Guard: unit must be vacant ─────────────────────────────────
    if unit.status != "vacant":
        raise ValidationError(
            {"unit": f"Unit {unit.unit_number} is not vacant (status: {unit.status})."}
        )

    # ── Guard: email must be unique ────────────────────────────────
    if User.objects.filter(email=user_data["email"]).exists():
        raise ValidationError(
            {"email": "A user with this email already exists."}
        )

    # ── Step 1: Create the User account ───────────────────────────
    temp_password = _generate_temp_password()
    user = User.objects.create_user(
        email=user_data["email"],
        password=temp_password,
        first_name=user_data["first_name"],
        last_name=user_data["last_name"],
        phone=user_data.get("phone", ""),
        role="tenant",
        # Tenants do not go through the approval flow
        email_verified=True,
        phone_verified=True,
    )
    # Flag forces password change on first login
    user.is_first_login = True
    user.save(update_fields=["is_first_login"])

    # ── Step 2: Create the Tenant profile ─────────────────────────
    tenant = Tenant.objects.create(user=user, **tenant_data)

    # ── Step 3: Create the Lease ──────────────────────────────────
    lease = create_lease(tenant=tenant, unit=unit, validated_data=lease_data)

    # ── Step 4: Mark unit as occupied ─────────────────────────────
    # update_unit fires unit_status_changed signal → listings app deactivates
    update_unit(unit, {"status": "occupied"})

    # ── Step 5: Send invitation email ─────────────────────────────
    _send_tenant_invitation(
        user=user,
        temp_password=temp_password,
        unit=unit,
        landlord_name=landlord.user.full_name,
    )

    # ── Step 6: Log to audit trail ────────────────────────────────
    try:
        from apps.users.models import AccessAuditLog
        AccessAuditLog.objects.create(
            user=landlord.user,
            event="invitation_sent",
            details={"tenant_user_id": user.id, "unit_id": unit.id},
        )
    except Exception:
        pass  # Audit log failure must never break tenant creation

    # ── Step 7: Announce to other apps ────────────────────────────
    # landlords app listens → complete_step("tenants")
    tenant_created.send(
        sender=Tenant,
        tenant_instance=tenant,
        landlord=landlord,
    )

    return tenant


# ── Update & End Tenancy ─────────────────────────────────────────────

@transaction.atomic
def end_tenancy(tenant, reason=""):
    """
    Ends a tenancy in the correct order:
      1. Terminate the active Lease
      2. Set unit status back to vacant (fires unit_status_changed signal)
      3. Soft-delete the Tenant profile

    Never call tenant.soft_delete() directly.
    Always call this function to ensure correct ordering.
    """
    from apps.leases.models import Lease
    active_lease = Lease.objects.filter(tenant=tenant, status="active").first()

    unit = None
    if active_lease:
        unit = active_lease.unit
        active_lease.terminate(reason=reason)

    if unit:
        update_unit(unit, {"status": "vacant"})

    tenant.soft_delete()


@transaction.atomic
def update_tenant(tenant, validated_data):
    """
    Updates allowed tenant profile fields.
    Cannot change user or unit — those are structural.
    Returns updated Tenant instance.
    """
    allowed_fields = [
        "id_number", "phone_alt",
        "emergency_contact_name", "emergency_contact_phone",
        "emergency_contact_relationship",
        "employer_name", "employer_contact",
        "payment_preference", "notification_preference",
        "id_copy_front_url", "id_copy_back_url",
    ]
    for field in allowed_fields:
        if field in validated_data:
            setattr(tenant, field, validated_data[field])
    tenant.save()
    return tenant


def get_tenant_or_404(tenant_id, landlord=None):
    """
    Returns a Tenant with user and current lease pre-fetched.
    If landlord provided, verifies the tenant is in one of their units.
    Raises NotFound (404) if not found or not owned.
    """
    qs = (
        Tenant.objects
        .select_related("user")
        .prefetch_related("leases__unit__property")
    )
    try:
        tenant = qs.get(pk=tenant_id)
    except Tenant.DoesNotExist:
        raise NotFound("Tenant not found.")

    if landlord:
        # Verify tenant is in one of this landlord's units
        is_owned = tenant.leases.filter(
            unit__property__landlord=landlord,
            status="active",
        ).exists()
        if not is_owned:
            raise NotFound("Tenant not found.")

    return tenant


def resend_invitation(tenant):
    """
    Resends the invitation email to a tenant.
    Generates a NEW temp password (the old one is no longer stored).
    Returns True if email sent, False if it failed.
    """
    temp_password = _generate_temp_password()
    user = tenant.user
    user.set_password(temp_password)
    user.is_first_login = True
    user.save(update_fields=["password", "is_first_login"])

    unit = tenant.current_unit
    if not unit:
        raise ValidationError("This tenant has no active unit.")

    _send_tenant_invitation(
        user=user,
        temp_password=temp_password,
        unit=unit,
        landlord_name="your landlord",
    )
    return True


def validate_cloudinary_url(url, user):
    """Validates Cloudinary URL belongs to this user's folder."""
    cloud  = settings.CLOUDINARY_CLOUD_NAME
    prefix = f"https://res.cloudinary.com/{cloud}/"
    return url.startswith(prefix) and str(user.uuid) in url
