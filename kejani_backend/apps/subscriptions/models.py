from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class SubscriptionPlan(models.Model):
    """
    Seeded via data migration. Never edited manually in production.
    features JSONB stores the complete feature set for this plan.
    This is the single source of truth for what each tier allows.
    """
    PLAN_TYPES = [
        ('landlord', 'Landlord'),
        ('property_manager', 'Property Manager'),
    ]

    name = models.CharField(max_length=100)          # "Solo", "Starter", "Growth"
    slug = models.SlugField(unique=True)              # "solo", "starter", "growth"
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPES)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2)
    annual_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Unit limits
    max_units = models.IntegerField()                 # 10, 30, 75, 150, -1 = unlimited
    max_properties = models.IntegerField()            # 2, 5, -1 = unlimited

    # SMS quota per month
    sms_quota = models.IntegerField(default=50)       # 50, 200, 500, 1000

    # The complete feature set for this plan — stored as JSONB
    # See seed data for the exact structure
    features = models.JSONField(default=dict)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'subscription_plans'
        ordering = ['monthly_price']

    def __str__(self):
        return f"{self.name} ({self.get_plan_type_display()})"


class Subscription(models.Model):
    """
    One active subscription per user at any time.
    Tracks trial period, billing cycle, and current status.
    """
    STATUS_CHOICES = [
        ('trial', 'Free Trial'),
        ('active', 'Active'),
        ('past_due', 'Past Due'),      # payment failed, grace period
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ]

    BILLING_CYCLE_CHOICES = [
        ('monthly', 'Monthly'),
        ('annual', 'Annual'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='subscription',
        db_index=True,
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,      # never delete a plan that has subscribers
        related_name='subscriptions'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='trial'
    )
    billing_cycle = models.CharField(
        max_length=10,
        choices=BILLING_CYCLE_CHOICES,
        default='monthly'
    )

    # Trial dates
    trial_start = models.DateTimeField(default=timezone.now)
    trial_end = models.DateTimeField(null=True, blank=True)   # trial_start + TRIAL_DURATION_DAYS

    # Billing dates
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    # SMS usage — resets monthly via Celery task
    sms_used_this_month = models.IntegerField(default=0)
    sms_reset_date = models.DateField(null=True, blank=True)

    # Cancellation
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions'

    def __str__(self):
        return f"{self.user.email} — {self.plan.name} ({self.get_status_display()})"

    def is_active(self):
        """
        The single method the rest of the codebase calls to
        check if a user can access the platform at all.
        """
        if self.status == 'trial':
            # Trial is active if it hasn't ended yet
            return self.trial_end is None or self.trial_end > timezone.now()
        return self.status in ('active', 'past_due')

    def get_sms_remaining(self):
        """Returns the number of SMS messages left in this billing cycle."""
        return max(0, self.plan.sms_quota - self.sms_used_this_month)

    def has_feature(self, feature_key):
        """
        The single method everything calls to check feature access.
        e.g. subscription.has_feature('bulk_sms')
        Delegates to the plan's feature set.
        """
        return self.plan.features.get(feature_key, False)

    def get_feature_limit(self, limit_key):
        """
        Returns numeric limits from the plan.
        e.g. subscription.get_feature_limit('max_units') → 30
        Returns -1 for unlimited.
        # It's a bit safer to pull from the fields if it's max_units/max_properties/sms_quota
        # directly, but we can also check the features JSON.
        """
        if limit_key == 'max_units':
            return self.plan.max_units
        if limit_key == 'max_properties':
            return self.plan.max_properties
        if limit_key == 'sms_quota':
            return self.plan.sms_quota
            
        return self.plan.features.get(limit_key, 0)
