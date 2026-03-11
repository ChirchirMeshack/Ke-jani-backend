import datetime
import hashlib
import time
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied

from .models import Property, Unit, PropertyPhoto, PropertyAmenity, PenaltyRule, AMENITY_CHOICES
from .exceptions import SubscriptionLimitError
from .signals import property_created, unit_created


# ── Subscription Limits ─────────────────────────────────────────────

def check_property_limits(landlord):
    """
    Raises SubscriptionLimitError if landlord has reached their property limit.
    Call this BEFORE creating a new Property.

    :param landlord: Landlord model instance
    :raises SubscriptionLimitError: if at or over limit
    """
    # Safely get limit from subscription, default to solo limits if none
    max_p = 2
    plan_name = "Solo"
    if hasattr(landlord.user, 'subscription'):
        max_p = landlord.user.subscription.get_feature_limit('max_properties')
        plan_name = landlord.user.subscription.plan.name

    if max_p == -1:  # -1 means unlimited
        return

    current = Property.objects.filter(landlord=landlord).count()
    if current >= max_p:
        raise SubscriptionLimitError(
            resource="properties",
            current=current,
            limit=max_p,
            plan_name=plan_name,
        )


def check_unit_limits(landlord):
    """
    Raises SubscriptionLimitError if landlord has reached their unit limit.
    Call this BEFORE creating a new Unit.
    Counts units across ALL of the landlord's properties.

    :param landlord: Landlord model instance
    :raises SubscriptionLimitError: if at or over limit
    """
    # Safely get limit from subscription, default to solo limits if none
    max_u = 10
    plan_name = "Solo"
    if hasattr(landlord.user, 'subscription'):
        max_u = landlord.user.subscription.get_feature_limit('max_units')
        plan_name = landlord.user.subscription.plan.name

    if max_u == -1:
        return

    current = Unit.objects.filter(
        property__landlord=landlord,
    ).count()
    if current >= max_u:
        raise SubscriptionLimitError(
            resource="units",
            current=current,
            limit=max_u,
            plan_name=plan_name,
        )


# ── Property Services ────────────────────────────────────────────────

def get_property_or_404(property_id, landlord=None):
    """
    Returns a Property with related data pre-fetched.
    If landlord is provided, also verifies ownership.
    Raises NotFound (HTTP 404) if not found or not owned.

    Always use this in views — never query Property directly.
    """
    qs = (
        Property.objects
        .select_related("landlord__user", "pm")
        .prefetch_related("amenities", "photos", "units")
    )
    try:
        prop = qs.get(pk=property_id)
    except Property.DoesNotExist:
        raise NotFound("Property not found.")

    if landlord and prop.landlord != landlord:
        raise NotFound("Property not found.")  # 404, not 403 — prevents enumeration

    return prop


def get_unit_or_404(unit_id, landlord=None):
    """
    Returns a Unit. Verifies ownership via property.landlord if landlord given.
    Raises NotFound (HTTP 404) if not found or not owned.
    """
    qs = Unit.objects.select_related("property__landlord__user")
    try:
        unit = qs.get(pk=unit_id)
    except Unit.DoesNotExist:
        raise NotFound("Unit not found.")

    if landlord and unit.property.landlord != landlord:
        raise NotFound("Unit not found.")

    return unit


def get_landlord_from_user(user):
    """
    Returns the Landlord profile for a user.
    Raises NotFound if user has no landlord profile.
    """
    try:
        return user.landlord_profile
    except Exception:
        raise NotFound("Landlord profile not found.")


@transaction.atomic
def create_property(landlord, validated_data):
    """
    Creates a new Property after checking subscription limits.
    Fires the property_created custom signal after creation.
    The default PenaltyRule is created automatically by post_save signal.

    :raises SubscriptionLimitError: if at property limit
    :returns: the created Property instance
    """
    check_property_limits(landlord)

    prop = Property.objects.create(
        landlord=landlord,
        **validated_data,
    )

    # Announce to other apps (landlords app listens to advance wizard)
    property_created.send(
        sender=Property,
        property_instance=prop,
        landlord=landlord,
    )

    return prop


@transaction.atomic
def update_property(prop, validated_data):
    """
    Updates allowed property fields. Does not allow changing landlord or PM.
    Returns the updated Property instance.
    """
    for field, value in validated_data.items():
        setattr(prop, field, value)
    prop.save()
    return prop


# ── Unit Services ────────────────────────────────────────────────────

@transaction.atomic
def create_unit(landlord, prop, validated_data):
    """
    Creates a Unit within a property after checking subscription limits.
    Fires unit_created signal. post_save signal updates actual_units.

    :raises SubscriptionLimitError: if at unit limit
    :returns: the created Unit instance
    """
    check_unit_limits(landlord)

    unit = Unit.objects.create(property=prop, **validated_data)
    # Note: unit_created signal is fired by post_save handler in signals.py.
    # We do NOT fire it here to avoid double-firing.
    return unit


@transaction.atomic
def update_unit(unit, validated_data):
    """
    Updates a unit. If status is changing, the pre_save handler
    in signals.py captures old_status so post_save can fire unit_status_changed.
    Returns the updated Unit instance.
    """
    for field, value in validated_data.items():
        setattr(unit, field, value)
    unit.save()
    return unit


# ── Amenity Services ─────────────────────────────────────────────────

@transaction.atomic
def set_amenities(prop, amenities_data):
    """
    Bulk-upserts all 10 amenity rows for a property.
    amenities_data is a dict: { "swimming_pool": True, "gym": False, ... }
    Missing keys default to False.

    Uses update_or_create so it is safe to call multiple times.
    Returns list of PropertyAmenity instances.
    """
    result = []
    for amenity_key, _ in AMENITY_CHOICES:
        obj, _ = PropertyAmenity.objects.update_or_create(
            property=prop,
            amenity_name=amenity_key,
            defaults={"available": amenities_data.get(amenity_key, False)},
        )
        result.append(obj)
    return result


# ── Photo Services ───────────────────────────────────────────────────

MAX_PHOTOS_PER_PROPERTY = 20

def add_photo(prop, user, photo_url, cloudinary_id="", unit=None):
    """
    Saves a Cloudinary URL as a new photo for a property or unit.
    Frontend uploads the file directly to Cloudinary, then calls this
    via POST /api/properties/<id>/photos/ with the resulting URL.

    :raises PermissionDenied: if property already has MAX_PHOTOS_PER_PROPERTY
    :returns: the created PropertyPhoto instance
    """
    current_count = PropertyPhoto.objects.filter(property=prop).count()
    if current_count >= MAX_PHOTOS_PER_PROPERTY:
        raise PermissionDenied(
            f"Maximum {MAX_PHOTOS_PER_PROPERTY} photos per property allowed. Remove some to add more."
        )

    next_order = current_count  # 0-indexed, append to end
    return PropertyPhoto.objects.create(
        property=prop,
        unit=unit,
        photo_url=photo_url,
        cloudinary_id=cloudinary_id,
        display_order=next_order,
        uploaded_by=user,
    )


@transaction.atomic
def reorder_photos(prop, ordered_ids):
    """
    Updates display_order for all photos of a property.
    ordered_ids: list of photo IDs in the new display order.
    e.g. [5, 2, 8, 1] means photo 5 is first, photo 2 is second, etc.

    Validates that all IDs belong to this property before updating.
    """
    prop_photo_ids = set(
        PropertyPhoto.objects.filter(property=prop).values_list("id", flat=True)
    )
    if set(ordered_ids) != prop_photo_ids:
        raise PermissionDenied("Photo IDs do not match this property's photos.")

    for order, photo_id in enumerate(ordered_ids):
        PropertyPhoto.objects.filter(pk=photo_id, property=prop).update(display_order=order)


def validate_cloudinary_url(url, user):
    """
    Checks that a URL is a legitimate Cloudinary URL for this user.
    Prevents a landlord submitting another landlord's photo URL.
    Returns True if valid.
    """
    cloud     = settings.CLOUDINARY_CLOUD_NAME
    prefix    = f"https://res.cloudinary.com/{cloud}/"
    return url.startswith(prefix) and str(user.uuid) in url


def get_cloudinary_upload_signature(user, upload_type):
    """
    Generates short-lived signed credentials for direct Cloudinary upload.
    USES SHA-1 — required by Cloudinary. Do NOT change to sha256.

    upload_type: "property_photo" | "unit_photo"
    Returns dict: { signature, timestamp, api_key, folder, cloud_name }
    """
    FOLDER_MAP = {
        'property_photo': f'ke-jani/properties/{user.uuid}/photos',
        'unit_photo':     f'ke-jani/properties/{user.uuid}/unit-photos',
    }
    timestamp = int(time.time())
    folder    = FOLDER_MAP.get(upload_type, f"ke-jani/properties/{user.uuid}/misc")

    params_to_sign = f"folder={folder}&timestamp={timestamp}"
    signature = hashlib.sha1(
        f"{params_to_sign}{settings.CLOUDINARY_SECRET}".encode("utf-8")
    ).hexdigest()

    return {
        "signature":  signature,
        "timestamp":  timestamp,
        "api_key":    settings.CLOUDINARY_API_KEY,
        "folder":     folder,
        "cloud_name": settings.CLOUDINARY_CLOUD_NAME,
    }


# ── Penalty Rule Services ─────────────────────────────────────────────

def get_or_create_property_penalty_rule(prop):
    """
    Returns the property-level penalty rule.
    Should always exist (created by post_save signal), but creates one
    as a safety net if missing.
    """
    rule, _ = PenaltyRule.objects.get_or_create(
        property=prop,
        unit=None,
        defaults={
            "penalty_type":    "percentage",
            "penalty_value":   Decimal("5.00"),
            "grace_period_days": 3,
            "effective_from":  datetime.date.today(),
        }
    )
    return rule


@transaction.atomic
def update_penalty_rule(rule, validated_data):
    """Updates a penalty rule (property-level or unit-level)."""
    for field, value in validated_data.items():
        setattr(rule, field, value)
    rule.save()
    return rule


@transaction.atomic
def set_unit_penalty_rule(unit, validated_data):
    """
    Creates or updates a unit-level penalty rule override.
    If no override exists yet, creates one.
    """
    rule, _ = PenaltyRule.objects.update_or_create(
        unit=unit,
        property=None,
        defaults={**validated_data, "effective_from": validated_data.get(
            "effective_from", datetime.date.today()
        )},
    )
    return rule
