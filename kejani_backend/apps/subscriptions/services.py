import datetime
from django.conf import settings
from django.utils import timezone
from django.db import transaction

from .models import SubscriptionPlan, Subscription


@transaction.atomic
def create_trial_subscription(user, plan_slug):
    """
    Creates a 30-day trial subscription for the user if they don't already have one.
    Also syncs the chosen plan slug to the user's profile.
    """
    # Check if a subscription already exists for this user
    if hasattr(user, 'subscription'):
        return user.subscription

    try:
        plan = SubscriptionPlan.objects.get(slug=plan_slug)
    except SubscriptionPlan.DoesNotExist:
        # Fallback to default plans based on user role
        if user.is_landlord:
            plan = SubscriptionPlan.objects.get(slug='solo')
        elif user.is_property_manager:
            plan = SubscriptionPlan.objects.get(slug='starter_pm')
        else:
            raise ValueError("User must be a landlord or property manager to subscribe.")

    # Calculate trial end date (30 days from now, configurable)
    trial_days = getattr(settings, 'TRIAL_DURATION_DAYS', 30)
    now = timezone.now()
    trial_end = now + datetime.timedelta(days=trial_days)

    # Create the subscription
    sub = Subscription.objects.create(
        user=user,
        plan=plan,
        status='trial',
        billing_cycle='monthly',
        trial_start=now,
        trial_end=trial_end,
        sms_used_this_month=0,
        sms_reset_date=now.date(),
    )

    # Sync to profile
    sync_subscription_tier_to_profile(user)

    return sub


def sync_subscription_tier_to_profile(user):
    """
    Syncs the active Subscription slug to the user's profile char field.
    """
    if not hasattr(user, 'subscription'):
        return

    plan_slug = user.subscription.plan.slug

    if getattr(user, 'is_landlord', False):
        try:
            profile = user.landlord_profile
            if profile.subscription_tier != plan_slug:
                profile.subscription_tier = plan_slug
                profile.save(update_fields=['subscription_tier'])
        except Exception:
            pass

    if getattr(user, 'is_property_manager', False):
        try:
            profile = user.pm_profile
            if profile.subscription_tier != plan_slug:
                profile.subscription_tier = plan_slug
                profile.save(update_fields=['subscription_tier'])
        except Exception:
            pass
