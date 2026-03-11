import hashlib
import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.exceptions import NotFound

from .models import Landlord
from apps.banking.models import MpesaAccount

User = get_user_model()


@transaction.atomic
def create_landlord_profile(user, id_number='', estimated_units_range=''):
    """
    Creates the Landlord profile row for a newly approved user.

    Called by the post_save signal on User when approval_status → 'approved'.
    Uses get_or_create so it is safe to call multiple times (idempotent).

    id_number and estimated_units_range come from the User instance's
    temp attributes (_id_number, _estimated_properties) set during registration.
    These attrs exist on the in-memory `instance` passed to the signal.

    Returns: (Landlord instance, created: bool)
    """
    landlord, created = Landlord.objects.get_or_create(
        user=user,
        defaults={
            'id_number':              id_number,
            'estimated_units_range':  estimated_units_range,
        },
    )
    return landlord, created


@transaction.atomic
def complete_profile_step(landlord, validated_data):
    """
    Processes Step 1 of the onboarding wizard.

    Updates: avatar_url, id_copy_front_url, id_copy_back_url,
             id_number (correction), subscription_tier, terms_accepted_at.

    Marks onboarding_step_profile_completed=True when ID copies are uploaded.
    Marks onboarding_step_mpesa_completed=True if M-Pesa account already exists.
    Triggers trial subscription creation (stub until apps/subscriptions/ is built).

    Returns: the updated Landlord instance.
    """
    update_fields = []

    for field in ['avatar_url', 'id_copy_front_url', 'id_copy_back_url',
                  'subscription_tier', 'id_number']:
        if field in validated_data:
            setattr(landlord, field, validated_data[field])
            update_fields.append(field)

    if validated_data.get('terms_agreed') and not landlord.terms_accepted_at:
        landlord.terms_accepted_at = timezone.now()
        update_fields.append('terms_accepted_at')

    if update_fields:
        landlord.save(update_fields=update_fields)

    # Trigger trial subscription creation (stub — will be implemented
    # when apps/subscriptions/ is built)
    if validated_data.get('subscription_tier'):
        _create_landlord_trial(landlord.user, validated_data['subscription_tier'])

    # Mark profile step complete when ID copies are present
    if landlord.id_copy_front_url and landlord.id_copy_back_url:
        landlord.complete_step('profile')

    # Mark M-Pesa step complete if account already exists
    # (landlord may have added M-Pesa during this same wizard session
    # via the banking endpoints before submitting this form)
    if MpesaAccount.objects.filter(user=landlord.user).exists():
        landlord.complete_step('mpesa')

    return landlord


def _create_landlord_trial(user, plan_slug):
    """
    Creates a 30-day trial subscription for the landlord.

    Calls create_trial_subscription from the subscriptions app,
    which also manages the syncing back to the Landlord profile.
    """
    from apps.subscriptions.services import create_trial_subscription
    
    # If plan_slug is empty, default it to the recommended plan (e.g. 'solo' for now)
    if not plan_slug:
        plan_slug = 'solo'
        
    create_trial_subscription(user=user, plan_slug=plan_slug)


def get_landlord_or_404(user):
    """
    Returns the Landlord profile for a user, with user already joined.
    Raises NotFound (HTTP 404) if no profile exists.

    Always use this in views instead of direct .get() calls.
    The select_related('user') prevents an extra DB query when the
    serializer accesses landlord.user.* fields.
    """
    try:
        return (
            Landlord.objects
            .select_related('user')
            .prefetch_related('user__mpesa_accounts', 'user__bank_accounts')
            .get(user=user)
        )
    except Landlord.DoesNotExist:
        raise NotFound('Landlord profile not found. Contact support if this is unexpected.')


def get_cloudinary_upload_signature(user, upload_type):
    """
    Generates short-lived credentials for direct-to-Cloudinary uploads.
    The frontend uses these to post a file directly to Cloudinary.
    Django never receives the file — only the resulting URL.

    IMPORTANT: Uses SHA-1 as required by Cloudinary's signing spec.
    Using SHA-256 produces invalid signatures that Cloudinary rejects.

    upload_type options: 'id_front', 'id_back', 'avatar'
    Returns: dict with signature, timestamp, api_key, folder, cloud_name.
    """
    FOLDER_MAP = {
        'id_front': f'ke-jani/ids/{user.uuid}/front',
        'id_back':  f'ke-jani/ids/{user.uuid}/back',
        'avatar':   f'ke-jani/avatars/{user.uuid}',
    }
    timestamp = int(time.time())
    folder    = FOLDER_MAP[upload_type]  # KeyError handled by view

    # Build the params string exactly as Cloudinary expects
    params_to_sign = f'folder={folder}&timestamp={timestamp}'

    # SHA-1 — required by Cloudinary. Do NOT change to sha256.
    signature = hashlib.sha1(
        f'{params_to_sign}{settings.CLOUDINARY_SECRET}'.encode('utf-8')
    ).hexdigest()

    return {
        'signature':  signature,
        'timestamp':  timestamp,
        'api_key':    settings.CLOUDINARY_API_KEY,
        'folder':     folder,
        'cloud_name': settings.CLOUDINARY_CLOUD_NAME,
    }


def validate_cloudinary_url(url, user):
    """
    Validates that a URL is a legitimate Cloudinary URL for THIS user.
    Checks two things:
    1. URL starts with the correct Cloudinary prefix for this account
    2. URL contains this user's UUID (prevents cross-user URL injection)

    Returns True if valid, False otherwise.
    """
    cloud_name      = settings.CLOUDINARY_CLOUD_NAME
    expected_prefix = f'https://res.cloudinary.com/{cloud_name}/'
    return (
        url.startswith(expected_prefix)
        and str(user.uuid) in url  # security: URL must be in this user's folder
    )
