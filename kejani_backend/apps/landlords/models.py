from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

# Used in registration form AND stored permanently on Landlord model.
# Also drives TIER_RECOMMENDATION below.
ESTIMATED_UNITS_CHOICES = [
    ('1-10',   '1 to 10 units'),
    ('11-30',  '11 to 30 units'),
    ('31-75',  '31 to 75 units'),
    ('76-150', '76 to 150 units'),
    ('150+',   'More than 150 units'),
]

SUBSCRIPTION_TIER_CHOICES = [
    ('solo',         'Solo — Ksh 1,500/mo'),
    ('starter',      'Starter — Ksh 2,500/mo'),
    ('growth',       'Growth — Ksh 6,000/mo'),
    ('professional', 'Professional — Ksh 10,000/mo'),
    ('enterprise',   'Enterprise — Custom'),
]

# Maps estimated units → recommended subscription slug.
# Used ONLY for pre-selecting the tier in the onboarding wizard.
# The landlord can always change the tier — this is a UX convenience, not a lock.
TIER_RECOMMENDATION = {
    '1-10':   'solo',
    '11-30':  'starter',
    '31-75':  'growth',
    '76-150': 'professional',
    '150+':   'enterprise',
}


class ActiveLandlordManager(models.Manager):
    """Default manager — filters out soft-deleted landlord profiles."""
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Landlord(models.Model):
    """
    Profile layer for landlord-specific data.
    Sits on top of apps.users.User (one-to-one).

    Created automatically by a post_save signal (see signals.py)
    when a User with role='landlord' has approval_status set to 'approved'.

    Access patterns:
      From a User:     request.user.landlord_profile
      From a Landlord: landlord.user

    Onboarding steps 2-4 are completed by other apps:
      - apps/properties/ marks 'property' and 'units' steps via landlord.complete_step()
      - apps/tenants/    marks 'tenants' step via landlord.complete_step()
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='landlord_profile',
        db_index=True,
    )

    # ── Identity ──────────────────────────────────────────────────
    id_number = models.CharField(
        max_length=20, blank=True,
        help_text='National ID number. Collected at registration, stored here.',
    )
    estimated_units_range = models.CharField(
        max_length=10,
        choices=ESTIMATED_UNITS_CHOICES,
        blank=True,
        help_text='Stored permanently for analytics + used to pre-select subscription tier.',
    )

    # ── Documents (Cloudinary URLs) ────────────────────────────────
    avatar_url        = models.URLField(blank=True)
    id_copy_front_url = models.URLField(blank=True, help_text='Front of National ID — Cloudinary URL.')
    id_copy_back_url  = models.URLField(blank=True, help_text='Back of National ID — Cloudinary URL.')

    # ── Subscription ──────────────────────────────────────────────
    subscription_tier = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_TIER_CHOICES,
        blank=True,
    )

    # ── Admin approval ────────────────────────────────────────────
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='landlords_approved',
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # ── KDPA compliance ───────────────────────────────────────────
    terms_accepted_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Timestamp when landlord accepted T&C. Required by KDPA 2019.',
    )

    # ── Onboarding wizard — server-side step completion ───────────
    # Step 1a: ID copies uploaded
    onboarding_step_profile_completed = models.BooleanField(default=False)
    # Step 1b: M-Pesa account added (part of Step 1 in the wizard)
    onboarding_step_mpesa_completed   = models.BooleanField(default=False)
    # Step 2: First property created (marked by apps/properties/)
    onboarding_step_property_completed = models.BooleanField(default=False)
    # Step 3: First unit added (marked by apps/properties/)
    onboarding_step_units_completed   = models.BooleanField(default=False)
    # Step 4: Optional — existing tenant added (marked by apps/tenants/)
    onboarding_step_tenants_completed = models.BooleanField(default=False)
    # Set when all REQUIRED steps are done (steps 1a, 1b, 2, 3)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    # ── Soft delete ───────────────────────────────────────────────
    deleted_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Soft delete. Set when landlord account is suspended.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects     = ActiveLandlordManager()
    objects_all = models.Manager()  # admin use only

    class Meta:
        db_table = 'landlords'
        verbose_name = 'Landlord'
        verbose_name_plural = 'Landlords'

    def __str__(self):
        return f'{self.user.full_name} (Landlord)'

    # ── Computed properties ────────────────────────────────────────

    @property
    def recommended_tier(self):
        """
        Suggested subscription slug based on units declared at signup.
        Pre-selects the tier card in the onboarding wizard.
        The landlord is free to choose a different tier.
        """
        return TIER_RECOMMENDATION.get(self.estimated_units_range, 'solo')

    @property
    def is_profile_complete(self):
        """True when minimum fields for admin review are present."""
        return bool(self.id_number and self.id_copy_front_url and self.id_copy_back_url)

    @property
    def onboarding_progress(self):
        """
        Returns a structured dict the frontend uses to drive the wizard.
        current_step is the first incomplete required step (1-based).
        Returns 'completed' if all required steps are done.
        """
        is_done = self.onboarding_completed_at is not None

        steps = {
            'profile':  self.onboarding_step_profile_completed,
            'mpesa':    self.onboarding_step_mpesa_completed,
            'property': self.onboarding_step_property_completed,
            'units':    self.onboarding_step_units_completed,
            'tenants':  self.onboarding_step_tenants_completed,  # optional
            'completed': is_done,
        }

        # Required steps in order. Tenant step is optional — not required.
        required_steps = ['profile', 'mpesa', 'property', 'units']
        if is_done:
            current_step = 'completed'
        else:
            current_step = next(
                (s for s in required_steps if not steps[s]),
                'tenants',   # all required done, show optional tenant step
            )

        done_count = sum(1 for s in required_steps if steps[s])
        percent    = int((done_count / len(required_steps)) * 100)

        return {**steps, 'current_step': current_step, 'percent_complete': percent}

    def complete_step(self, step_name):
        """
        Marks a wizard step as complete and saves.
        Called by this app (step 'profile', 'mpesa') and by signals
        from other apps ('property', 'units', 'tenants').

        Automatically calls mark_onboarding_complete() if all required
        steps are now done.

        Idempotent — safe to call multiple times.
        """
        field_map = {
            'profile':  'onboarding_step_profile_completed',
            'mpesa':    'onboarding_step_mpesa_completed',
            'property': 'onboarding_step_property_completed',
            'units':    'onboarding_step_units_completed',
            'tenants':  'onboarding_step_tenants_completed',
        }
        field = field_map.get(step_name)
        if not field:
            raise ValueError(f'Unknown step name: {step_name}. Valid: {list(field_map)}')

        if not getattr(self, field):
            setattr(self, field, True)
            self.save(update_fields=[field])

        # Check if all required steps are now complete
        if all([
            self.onboarding_step_profile_completed,
            self.onboarding_step_mpesa_completed,
            self.onboarding_step_property_completed,
            self.onboarding_step_units_completed,
        ]):
            self._mark_onboarding_complete()

    def _mark_onboarding_complete(self):
        """Sets onboarding_completed_at. Idempotent."""
        if not self.onboarding_completed_at:
            self.onboarding_completed_at = timezone.now()
            self.save(update_fields=['onboarding_completed_at'])

    def soft_delete(self):
        """Suspends a landlord account. Does not delete the DB row."""
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])
