from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from functools import wraps
from django.http import JsonResponse


def get_user_subscription(user):
    """
    Safe getter — returns None if no subscription exists.
    """
    try:
        if user.is_authenticated:
            return user.subscription
    except Exception:
        pass
    return None


class SubscriptionActive(BasePermission):
    """
    DRF permission — blocks any request from a user whose
    subscription has expired or been cancelled.
    """
    message = {
        "error": "subscription_required",
        "message": "Your subscription has expired. Please renew to continue.",
        "action_url": "/billing"
    }

    def has_permission(self, request, view):
        sub = get_user_subscription(request.user)
        if sub is None:
            raise PermissionDenied({
                "error": "subscription_required",
                "message": "You do not have an active subscription.",
                "action_url": "/billing"
            })
        if not sub.is_active():
            raise PermissionDenied(self.message)
        return True


class RequireFeature(BasePermission):
    """
    DRF permission class factory.
    Usage in a view:
        permission_classes = [IsAuthenticated, RequireFeature('bulk_sms')]
    """
    def __init__(self, feature_key):
        self.feature_key = feature_key

    def has_permission(self, request, view):
        sub = get_user_subscription(request.user)
        if sub is None or not sub.is_active():
            raise PermissionDenied({
                "error": "subscription_required",
                "message": "You need an active subscription to use this feature.",
                "action_url": "/billing"
            })

        if not sub.has_feature(self.feature_key):
            raise PermissionDenied({
                "error": "feature_not_available",
                "feature": self.feature_key,
                "current_plan": sub.plan.slug,
                "message": f"This feature is not available on your {sub.plan.name} plan.",
                "upgrade_prompt": _get_upgrade_prompt(sub.plan.slug, self.feature_key),
                "action_url": "/billing/upgrade"
            })
        return True

    def __call__(self):
        # Allows usage as permission_classes = [RequireFeature('bulk_sms')]
        return self


def _get_upgrade_prompt(current_plan_slug, feature_key):
    """
    Returns a human-readable upgrade message for the frontend to display.
    """
    FEATURE_PLAN_MAP = {
        'bulk_sms': 'Starter',
        'sms_reminders': 'Starter',
        'report_pdf_export': 'Starter',
        'property_manager_delegation': 'Growth',
        'white_label_receipts': 'Growth',
        'utility_billing_automated': 'Growth',
        'listing_analytics_full': 'Growth',
        'api_access': 'Enterprise',
    }
    required_plan = FEATURE_PLAN_MAP.get(feature_key, 'a higher plan')
    return f"Upgrade to {required_plan} to unlock this feature."


def require_feature(feature_key):
    """
    Python decorator for non-DRF views or service functions.
    Usage:
        @require_feature('bulk_sms')
        def send_bulk_sms(request, ...):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            sub = get_user_subscription(request.user)
            if sub is None or not sub.is_active():
                return JsonResponse({
                    "error": "subscription_required",
                    "action_url": "/billing"
                }, status=403)
            if not sub.has_feature(feature_key):
                return JsonResponse({
                    "error": "feature_not_available",
                    "feature": feature_key,
                    "current_plan": sub.plan.slug,
                    "action_url": "/billing/upgrade"
                }, status=403)
            return func(request, *args, **kwargs)
        return wrapper
    return decorator
