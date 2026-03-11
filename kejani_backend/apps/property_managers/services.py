import secrets
import hashlib
import time
import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError, PermissionDenied

from .models import (
    PropertyManager, PmServiceArea, PmAssignmentRequest, CommissionRecord,
    PM_TIER_LIMITS,
)
from .signals import pm_assigned

User = get_user_model()
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  Tier Limits & Helpers
# ══════════════════════════════════════════════════════════════════════

class PmLimitError(Exception):
    """Raised when a PM would exceed their tier unit limit."""
    def __init__(self, current, limit, plan):
        self.resource = "units"
        self.current  = current
        self.limit    = limit
        self.plan     = plan
        super().__init__(f"PM plan {plan!r} allows {limit} units. Currently managing {current}.")

    def to_response_dict(self):
        return {
            "error":       "pm_limit_exceeded",
            "resource":    self.resource,
            "current":     self.current,
            "limit":       self.limit,
            "plan":        self.plan,
            "message":     str(self),
            "upgrade_url": "/settings/subscription/",
        }


def check_pm_unit_limit(pm, new_units_to_add):
    """Checks whether accepting a new property would exceed unit limit."""
    tier   = pm.subscription_tier
    limits = PM_TIER_LIMITS.get(tier, {})
    max_u  = limits.get("max_units", -1)

    if max_u == -1:
        return  # Unlimited (enterprise_pm)

    current = pm.total_units_managed
    if current + new_units_to_add > max_u:
        raise PmLimitError(current=current, limit=max_u, plan=tier)


def get_pm_or_404(pm_id, user=None):
    """Returns a PropertyManager by ID. Verifies ownership if user given."""
    try:
        pm = PropertyManager.objects.select_related("user").get(pk=pm_id)
    except PropertyManager.DoesNotExist:
        raise NotFound("Property manager not found.")
    if user and pm.user != user:
        raise NotFound("Property manager not found.")
    return pm


def get_pm_from_user(user):
    """Returns the PM profile for the logged-in PM user."""
    try:
        return user.pm_profile
    except PropertyManager.DoesNotExist:
        raise PermissionDenied("No property manager profile found for this user.")


# ══════════════════════════════════════════════════════════════════════
#  PM Profile Services
# ══════════════════════════════════════════════════════════════════════

@transaction.atomic
def update_pm_profile(pm, validated_data):
    """Updates allowed PM profile fields."""
    allowed_fields = [
        "id_number", "company_name", "bio",
        "commission_rate",
        "id_copy_front_url", "id_copy_back_url",
    ]
    for field in allowed_fields:
        if field in validated_data:
            setattr(pm, field, validated_data[field])
    pm.save()
    return pm


def complete_pm_onboarding_step(pm, step_name):
    """Advances the PM onboarding wizard. Returns updated progress dict."""
    pm.complete_step(step_name)
    pm.refresh_from_db()
    return pm.onboarding_progress


def validate_cloudinary_url(url, user):
    """Validates that the Cloudinary URL belongs to this user's folder."""
    cloud  = getattr(settings, 'CLOUDINARY_CLOUD_NAME', '')
    prefix = f"https://res.cloudinary.com/{cloud}/"
    return url.startswith(prefix) and str(user.uuid) in url


def get_cloudinary_upload_signature(user, upload_type):
    """Generates a signed upload URL for Cloudinary."""
    VALID_TYPES = ("pm_id_front", "pm_id_back")
    if upload_type not in VALID_TYPES:
        raise ValidationError({"type": f"Must be one of: {VALID_TYPES}"})
    timestamp = int(time.time())
    folder    = f"ke-jani/pm-ids/{user.uuid}/{upload_type}"
    params    = f"folder={folder}&timestamp={timestamp}"
    signature = hashlib.sha1(
        f"{params}{settings.CLOUDINARY_SECRET}".encode()
    ).hexdigest()
    return {
        "signature":  signature,
        "timestamp":  timestamp,
        "api_key":    settings.CLOUDINARY_API_KEY,
        "folder":     folder,
        "cloud_name": settings.CLOUDINARY_CLOUD_NAME,
    }


# ══════════════════════════════════════════════════════════════════════
#  Service Area Services
# ══════════════════════════════════════════════════════════════════════

def add_service_area(pm, county, area=""):
    """Adds a service area for the PM. Idempotent via get_or_create."""
    return PmServiceArea.objects.get_or_create(pm=pm, county=county, area=area)


def remove_service_area(pm, service_area_id):
    """Removes a service area by ID, verifying ownership."""
    try:
        area = PmServiceArea.objects.get(pk=service_area_id, pm=pm)
    except PmServiceArea.DoesNotExist:
        raise NotFound("Service area not found.")
    area.delete()


# ══════════════════════════════════════════════════════════════════════
#  Assignment Services — Landlord Side
# ══════════════════════════════════════════════════════════════════════

@transaction.atomic
def assign_existing_pm(landlord, pm, property_instance, terms_data):
    """
    Creates a PmAssignmentRequest for an existing PM.
    Does NOT change the property yet — PM must accept first.
    """
    # Guard: property must belong to this landlord
    if property_instance.landlord != landlord:
        raise PermissionDenied("You do not own this property.")

    # Guard: property must not already be delegated
    if property_instance.management_mode == "delegated":
        raise ValidationError(
            {"property": "This property already has an assigned property manager."}
        )

    # Guard: no existing pending request
    if PmAssignmentRequest.objects.filter(
        property=property_instance, status="pending"
    ).exists():
        raise ValidationError(
            {"property": "There is already a pending assignment request for this property."}
        )

    # Guard: PM must be approved
    if not pm.is_approved:
        raise ValidationError({"pm": "This property manager has not been approved yet."})

    request = PmAssignmentRequest.objects.create(
        landlord=landlord,
        pm=pm,
        property=property_instance,
        commission_rate=terms_data.get("commission_rate", pm.commission_rate),
        can_add_tenants=terms_data.get("can_add_tenants", True),
        can_handle_maintenance=terms_data.get("can_handle_maintenance", True),
        expense_approval_threshold=terms_data.get("expense_approval_threshold", 10000),
        proposed_start_date=terms_data.get("proposed_start_date"),
    )

    _notify_pm_assignment_request(pm, property_instance, landlord)
    return request


def _generate_invite_token():
    """Generates a cryptographically secure 48-char URL-safe token."""
    return secrets.token_urlsafe(36)


@transaction.atomic
def invite_new_pm(landlord, invite_data, property_instance, terms_data):
    """
    Invites a person NOT yet on the platform to become a PM.
    Creates PmAssignmentRequest with pm=NULL and invite token.
    """
    if property_instance.landlord != landlord:
        raise PermissionDenied("You do not own this property.")

    if property_instance.management_mode == "delegated":
        raise ValidationError({"property": "This property already has an assigned PM."})

    if User.objects.filter(email=invite_data["email"]).exists():
        raise ValidationError(
            {"email": "This person already has a Ke-jani account. Use Assign Existing PM instead."}
        )

    token = _generate_invite_token()
    request = PmAssignmentRequest.objects.create(
        landlord=landlord,
        pm=None,
        property=property_instance,
        commission_rate=terms_data.get("commission_rate", 10),
        can_add_tenants=terms_data.get("can_add_tenants", True),
        can_handle_maintenance=terms_data.get("can_handle_maintenance", True),
        expense_approval_threshold=terms_data.get("expense_approval_threshold", 10000),
        invite_email=invite_data["email"],
        invite_name=invite_data["name"],
        invite_phone=invite_data.get("phone", ""),
        invite_token=token,
        invite_token_expires_at=timezone.now() + timedelta(days=7),
    )

    _send_pm_invite_email(
        email=invite_data["email"],
        name=invite_data["name"],
        token=token,
        property_instance=property_instance,
        landlord=landlord,
    )
    return request


def _notify_pm_assignment_request(pm, property_instance, landlord):
    """Notifies an existing PM of a new assignment request."""
    try:
        frontend_url = getattr(settings, "FRONTEND_URL", "https://ke-jani.com")
        send_mail(
            subject=f"New property assignment request — {property_instance.name}",
            message=(
                f"Hi {pm.user.first_name},\n\n"
                f"{landlord.user.full_name} has requested that you manage "
                f"{property_instance.name}.\n\n"
                f"Log in to review and respond: {frontend_url}/assignments/"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[pm.user.email],
            fail_silently=True,
        )
    except Exception:
        pass


def _send_pm_invite_email(email, name, token, property_instance, landlord):
    """Sends token-based invite email to a new (unregistered) PM."""
    frontend_url = getattr(settings, "FRONTEND_URL", "https://ke-jani.com")
    invite_url   = f"{frontend_url}/pm-invite/{token}"
    try:
        send_mail(
            subject=f"You've been invited to manage {property_instance.name} on Ke-jani",
            message=(
                f"Hi {name},\n\n"
                f"{landlord.user.full_name} has invited you to manage "
                f"{property_instance.name} via Ke-jani.\n\n"
                f"Accept the invitation (link expires in 7 days):\n"
                f"{invite_url}\n\n"
                "— The Ke-jani Team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════
#  Assignment Services — PM Side
# ══════════════════════════════════════════════════════════════════════

@transaction.atomic
def accept_assignment(pm, assignment_request):
    """
    PM accepts an assignment request. Updates Property atomically.
    Fires pm_assigned signal.
    """
    if assignment_request.status != "pending":
        raise ValidationError(
            {"assignment": f"Cannot accept a request with status '{assignment_request.status}'."}
        )
    if assignment_request.pm != pm:
        raise PermissionDenied("This request is not addressed to you.")

    # Check unit limits
    new_units = assignment_request.property.actual_units
    check_pm_unit_limit(pm, new_units)

    # Update request
    assignment_request.status       = "accepted"
    assignment_request.responded_at = timezone.now()
    assignment_request.save(update_fields=["status", "responded_at", "updated_at"])

    # Update Property
    prop = assignment_request.property
    prop.management_mode              = "delegated"
    prop.property_manager             = pm
    prop.pm_commission_rate           = assignment_request.commission_rate
    prop.pm_assigned_at               = timezone.now()
    prop.pm_can_add_tenants           = assignment_request.can_add_tenants
    prop.pm_can_handle_maintenance    = assignment_request.can_handle_maintenance
    prop.pm_expense_approval_threshold = assignment_request.expense_approval_threshold
    prop.save(update_fields=[
        "management_mode", "property_manager", "pm_commission_rate",
        "pm_assigned_at", "pm_can_add_tenants", "pm_can_handle_maintenance",
        "pm_expense_approval_threshold", "updated_at",
    ])

    # Fire signal
    pm_assigned.send(
        sender=PropertyManager,
        pm_instance=pm,
        property_instance=prop,
        assignment_request=assignment_request,
    )

    return assignment_request


@transaction.atomic
def decline_assignment(pm, assignment_request, reason=""):
    """PM declines an assignment request."""
    if assignment_request.status != "pending":
        raise ValidationError(
            {"assignment": f"Cannot decline a request with status '{assignment_request.status}'."}
        )
    if assignment_request.pm != pm:
        raise PermissionDenied("This request is not addressed to you.")

    assignment_request.status         = "declined"
    assignment_request.responded_at   = timezone.now()
    assignment_request.decline_reason = reason
    assignment_request.save(update_fields=[
        "status", "responded_at", "decline_reason", "updated_at"
    ])
    return assignment_request


@transaction.atomic
def accept_pm_invite(token, user_data):
    """
    Token-based PM signup flow.
    Creates User + PM profile + accepts assignment in one atomic call.
    """
    try:
        request = PmAssignmentRequest.objects.select_related(
            "landlord__user", "property"
        ).get(invite_token=token, status="pending")
    except PmAssignmentRequest.DoesNotExist:
        raise ValidationError({"token": "Invalid or already used invitation link."})

    if not request.is_invite_token_valid:
        raise ValidationError({"token": "This invitation link has expired."})

    if user_data["email"].lower() != request.invite_email.lower():
        raise ValidationError({"email": "Email does not match the invitation."})

    if User.objects.filter(email=user_data["email"]).exists():
        raise ValidationError({"email": "An account with this email already exists."})

    # Create User
    user = User.objects.create_user(
        email=user_data["email"],
        password=user_data["password"],
        first_name=user_data["first_name"],
        last_name=user_data["last_name"],
        phone=user_data.get("phone", ""),
        role="property_manager",
        email_verified=True,
        phone_verified=True,
    )

    # Create PM profile (auto-approved via invite)
    pm = PropertyManager.objects.create(
        user=user,
        approval_status="approved",
        approved_at=timezone.now(),
        subscription_active=True,
    )

    # Link PM to the request and accept
    request.pm = pm
    request.save(update_fields=["pm", "updated_at"])
    accept_assignment(pm=pm, assignment_request=request)

    return pm, request


# ══════════════════════════════════════════════════════════════════════
#  Remove / Resign
# ══════════════════════════════════════════════════════════════════════

@transaction.atomic
def remove_pm_from_property(landlord, property_instance):
    """Landlord removes PM from a property (returns to self-managed)."""
    if property_instance.landlord != landlord:
        raise PermissionDenied("You do not own this property.")

    if property_instance.management_mode != "delegated":
        raise ValidationError({"property": "This property is not currently delegated."})

    property_instance.management_mode              = "self_managed"
    property_instance.property_manager             = None
    property_instance.pm_commission_rate            = None
    property_instance.pm_assigned_at               = None
    property_instance.pm_can_add_tenants           = True
    property_instance.pm_can_handle_maintenance    = True
    property_instance.pm_expense_approval_threshold = None
    property_instance.save(update_fields=[
        "management_mode", "property_manager", "pm_commission_rate",
        "pm_assigned_at", "pm_can_add_tenants", "pm_can_handle_maintenance",
        "pm_expense_approval_threshold", "updated_at",
    ])


@transaction.atomic
def pm_resign_from_property(pm, property_instance):
    """PM resigns from managing a property. Notifies landlord."""
    if property_instance.property_manager != pm:
        raise PermissionDenied("You are not managing this property.")

    property_instance.management_mode              = "self_managed"
    property_instance.property_manager             = None
    property_instance.pm_commission_rate            = None
    property_instance.pm_assigned_at               = None
    property_instance.pm_can_add_tenants           = True
    property_instance.pm_can_handle_maintenance    = True
    property_instance.pm_expense_approval_threshold = None
    property_instance.save(update_fields=[
        "management_mode", "property_manager", "pm_commission_rate",
        "pm_assigned_at", "pm_can_add_tenants", "pm_can_handle_maintenance",
        "pm_expense_approval_threshold", "updated_at",
    ])

    # Notify landlord
    try:
        send_mail(
            subject=f"Property manager resigned from {property_instance.name}",
            message=(
                f"Hi {property_instance.landlord.user.first_name},\n\n"
                f"{pm.user.full_name} has resigned from managing {property_instance.name}.\n"
                "The property is now self-managed."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[property_instance.landlord.user.email],
            fail_silently=True,
        )
    except Exception:
        pass
