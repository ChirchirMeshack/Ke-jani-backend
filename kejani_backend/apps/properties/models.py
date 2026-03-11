from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import builtins

User = get_user_model()


# ── All 47 Kenyan Counties ──────────────────────────────────────────
KENYA_COUNTIES = [
    ('nairobi',          'Nairobi City'),
    ('mombasa',          'Mombasa'),
    ('kwale',            'Kwale'),
    ('kilifi',           'Kilifi'),
    ('tana_river',       'Tana River'),
    ('lamu',             'Lamu'),
    ('taita_taveta',     'Taita-Taveta'),
    ('garissa',          'Garissa'),
    ('wajir',            'Wajir'),
    ('mandera',          'Mandera'),
    ('marsabit',         'Marsabit'),
    ('isiolo',           'Isiolo'),
    ('meru',             'Meru'),
    ('tharaka_nithi',    'Tharaka-Nithi'),
    ('embu',             'Embu'),
    ('kitui',            'Kitui'),
    ('machakos',         'Machakos'),
    ('makueni',          'Makueni'),
    ('nyandarua',        'Nyandarua'),
    ('nyeri',            'Nyeri'),
    ('kirinyaga',        'Kirinyaga'),
    ('muranga',          "Murang'a"),
    ('kiambu',           'Kiambu'),
    ('turkana',          'Turkana'),
    ('west_pokot',       'West Pokot'),
    ('samburu',          'Samburu'),
    ('trans_nzoia',      'Trans-Nzoia'),
    ('uasin_gishu',      'Uasin Gishu'),
    ('elgeyo_marakwet',  'Elgeyo-Marakwet'),
    ('nandi',            'Nandi'),
    ('baringo',          'Baringo'),
    ('laikipia',         'Laikipia'),
    ('nakuru',           'Nakuru'),
    ('narok',            'Narok'),
    ('kajiado',          'Kajiado'),
    ('kericho',          'Kericho'),
    ('bomet',            'Bomet'),
    ('kakamega',         'Kakamega'),
    ('vihiga',           'Vihiga'),
    ('bungoma',          'Bungoma'),
    ('busia',            'Busia'),
    ('siaya',            'Siaya'),
    ('kisumu',           'Kisumu'),
    ('homa_bay',         'Homa Bay'),
    ('migori',           'Migori'),
    ('kisii',            'Kisii'),
    ('nyamira',          'Nyamira'),
]

PROPERTY_TYPE_CHOICES = [
    ('flat',        'Flat / Apartment'),
    ('house',       'House / Bungalow'),
    ('bedsitter',   'Bedsitter'),
    ('office',      'Office Space'),
    ('plot',        'Plot / Land'),
    ('commercial',  'Commercial Space'),
    ('other',       'Other'),
]

LISTING_TYPE_CHOICES = [
    ('rent', 'For Rent'),
    ('sale', 'For Sale'),
    ('both', 'Rent & Sale'),
]

MANAGEMENT_MODE_CHOICES = [
    ('self_managed', 'Self Managed'),
    ('delegated',    'Delegated to PM'),
]

AMENITY_CHOICES = [
    ('swimming_pool',       'Swimming Pool'),
    ('gym',                 'Gym'),
    ('backup_generator',    'Backup Generator'),
    ('24hr_security',       '24-Hour Security'),
    ('cctv',                'CCTV'),
    ('parking',             'Parking'),
    ('elevator',            'Elevator / Lift'),
    ('wifi',                'Internet / Wi-Fi'),
    ('playground',          'Playground'),
    ('pet_friendly',        'Pet Friendly'),
]

UNIT_STATUS_CHOICES = [
    ('vacant',      'Vacant'),
    ('occupied',    'Occupied'),
    ('maintenance', 'Under Maintenance'),
]

PENALTY_TYPE_CHOICES = [
    ('percentage', 'Percentage of rent'),
    ('fixed',      'Fixed amount (Ksh)'),
]


# ── Managers ────────────────────────────────────────────────────────

class ActiveManager(models.Manager):
    """Default manager — excludes soft-deleted rows."""
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


# ── Property ────────────────────────────────────────────────────────

class Property(models.Model):
    """
    One row per physical building or plot.
    A landlord owns many properties.
    A property may be delegated to one PM (pm field, nullable until PM app built).

    Two unit count fields:
      declared_units — what landlord said in the wizard (never auto-changed)
      actual_units   — auto-synced by post_save signal on Unit

    The gap between them drives onboarding nudges:
      "You said 20 units — you have only added 8."
    """

    # ── Ownership ─────────────────────────────────────────────────
    landlord = models.ForeignKey(
        'landlords.Landlord',
        on_delete=models.CASCADE,
        related_name='properties',
        db_index=True,
    )
    # PM fields — nullable until apps/property_managers/ is built.
    # property_managers app will populate these when a landlord delegates.
    pm = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='managed_properties',
        db_index=True,
        help_text='Set by property_managers app when landlord delegates.',
    )
    management_mode = models.CharField(
        max_length=20,
        choices=MANAGEMENT_MODE_CHOICES,
        default='self_managed',
    )
    pm_assigned_at = models.DateTimeField(null=True, blank=True)

    # ── Basic Info ────────────────────────────────────────────────
    name          = models.CharField(max_length=200)
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPE_CHOICES)
    listing_type  = models.CharField(max_length=10, choices=LISTING_TYPE_CHOICES, default="rent")
    description   = models.TextField(max_length=1000, blank=True)

    # ── Location ──────────────────────────────────────────────────
    county         = models.CharField(max_length=30, choices=KENYA_COUNTIES)
    area           = models.CharField(max_length=100)
    estate         = models.CharField(max_length=100, blank=True)
    street_address = models.CharField(max_length=255, blank=True)
    # Decimal fields for GPS coordinates — more precise than FloatField
    latitude  = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # ── Unit counts ───────────────────────────────────────────────
    # declared_units: from wizard ("how many units does this building have?")
    # Never auto-updated. Used for setup-completion nudges.
    declared_units = models.IntegerField(default=1)
    # actual_units: auto-maintained by post_save signal on Unit.
    # Always reflects reality. Used for occupancy % and limit checks.
    actual_units   = models.IntegerField(default=0)

    # ── Status ────────────────────────────────────────────────────
    is_active  = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects     = ActiveManager()
    objects_all = models.Manager()  # admin use: includes soft-deleted

    class Meta:
        db_table = 'properties'
        verbose_name = 'Property'
        verbose_name_plural = 'Properties'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.landlord.user.full_name})"

    @property
    def occupancy_percent(self):
        """Occupied units as % of actual_units. Returns 0 if no units."""
        if not self.actual_units:
            return 0
        occupied = self.units.filter(status="occupied").count()
        return int((occupied / self.actual_units) * 100)

    @property
    def setup_gap(self):
        """How many units are declared but not yet added. For onboarding nudge."""
        return max(0, self.declared_units - self.actual_units)

    def soft_delete(self):
        """Soft-deletes property and all its units."""
        self.deleted_at = timezone.now()
        self.is_active  = False
        self.save(update_fields=["deleted_at", "is_active"])
        # Cascade soft-delete to units
        self.units.filter(deleted_at__isnull=True).update(
            deleted_at=self.deleted_at,
            status="maintenance",
        )


# ── Unit ────────────────────────────────────────────────────────────

class Unit(models.Model):
    """
    One row per rentable space within a property.
    A unit can be a flat, bedsitter, office bay, shop, etc.

    Status transitions:
      vacant → occupied     (when tenant lease is created)
      occupied → vacant     (when lease ends / tenant moves out)
      any → maintenance     (manual, e.g. renovation)
      maintenance → vacant  (manual, after repairs)

    unit_status_changed signal is fired on every status change.
    apps/listings/ will listen to auto-publish/unpublish listings.
    """

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='units',
        db_index=True,
    )

    # ── Identity ──────────────────────────────────────────────────
    unit_number = models.CharField(
        max_length=20,
        help_text='e.g. A1, 101, Ground Floor Left',
    )

    # ── Physical details ──────────────────────────────────────────
    bedrooms    = models.IntegerField(default=0,   help_text="0 = bedsitter/studio")
    bathrooms   = models.IntegerField(default=1)
    size_sqft   = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    floor_level = models.IntegerField(null=True, blank=True, help_text="Ground=0, 1st=1 etc.")
    furnished   = models.BooleanField(default=False)
    has_parking = models.BooleanField(default=False)

    # ── Pricing ───────────────────────────────────────────────────
    # rent_amount: for listing_type=rent
    # sale_price:  for listing_type=sale
    # Both may be set if property listing_type="both"
    rent_amount    = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sale_price     = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # ── Status ────────────────────────────────────────────────────
    status = models.CharField(max_length=15, choices=UNIT_STATUS_CHOICES, default='vacant')

    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects     = ActiveManager()
    objects_all = models.Manager()

    class Meta:
        db_table = 'units'
        verbose_name = 'Unit'
        verbose_name_plural = 'Units'
        # Unique unit number per property
        unique_together = [('property', 'unit_number')]

    def __str__(self):
        return f"Unit {self.unit_number} — {self.property.name}"

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    @builtins.property
    def effective_penalty_rule(self):
        """
        Returns the penalty rule that applies to this unit.
        Unit-level override takes priority over property-level default.
        Returns None if no rule is set anywhere (should not happen —
        property always gets a default rule on creation).
        """
        unit_rule = PenaltyRule.objects.filter(unit=self).first()
        if unit_rule:
            return unit_rule
        return PenaltyRule.objects.filter(property=self.property).first()


# ── PropertyAmenity ─────────────────────────────────────────────────

class PropertyAmenity(models.Model):
    """
    Amenities checklist — one row per amenity per property.
    10 amenity types (from onboarding wizard checklist).
    Bulk-upserted: all 10 amenity rows are written in one service call.
    """
    property     = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='amenities',
        db_index=True,
    )
    amenity_name = models.CharField(max_length=30, choices=AMENITY_CHOICES)
    available    = models.BooleanField(default=False)

    class Meta:
        db_table = 'property_amenities'
        unique_together = [('property', 'amenity_name')]
        verbose_name = 'Property Amenity'

    def __str__(self):
        return f"{self.get_amenity_name_display()} — {self.property.name} ({'Yes' if self.available else 'No'})"


# ── PropertyPhoto ────────────────────────────────────────────────────

class PropertyPhoto(models.Model):
    """
    Photos for both properties and individual units.
    unit is nullable — if set, photo belongs to that unit.
    If unit is None, photo belongs to the property as a whole.

    Max 20 photos per property (enforced in service layer).
    display_order is an integer — frontend drag-and-drop updates it
    via PATCH /api/properties/<id>/photos/reorder/
    """
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='photos',
        db_index=True,
    )
    # If set, this photo is for a specific unit (e.g. unit interior)
    # If None, this is a property-level photo (exterior, common areas)
    unit = models.ForeignKey(
        Unit,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='photos',
        db_index=True,
    )
    cloudinary_id = models.CharField(max_length=255, blank=True)
    photo_url     = models.URLField()
    display_order = models.IntegerField(default=0)
    uploaded_by   = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_photos',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'property_photos'
        ordering = ['display_order', 'created_at']
        verbose_name = 'Property Photo'

    def __str__(self):
        target = f"Unit {self.unit.unit_number}" if self.unit else "Property"
        return f"{target} photo — {self.property.name}"


# ── PenaltyRule ──────────────────────────────────────────────────────

class PenaltyRule(models.Model):
    """
    Late payment penalty configuration.
    ONE TABLE for both property-level defaults and unit-level overrides.

    Exactly ONE of property or unit must be set (not both, not neither).
    This is enforced by a PostgreSQL CHECK constraint added in the migration
    via RunSQL. Django does not enforce this automatically.

    Lookup order in payments app:
      1. Check PenaltyRule.objects.filter(unit=unit) — use if exists
      2. Fall back to PenaltyRule.objects.filter(property=unit.property)

    Default rule (property-level) is created automatically by
    post_save signal on Property: 5%, 3-day grace period.
    """
    # Exactly one of these is set — CHECK constraint enforces this in DB.
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='penalty_rules',
        db_index=True,
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='penalty_rules',
        db_index=True,
    )

    penalty_type  = models.CharField(max_length=15, choices=PENALTY_TYPE_CHOICES)
    penalty_value = models.DecimalField(
        max_digits=8, decimal_places=2,
        help_text='If percentage: value is 5.00 = 5%. If fixed: value is Ksh amount.',
    )
    grace_period_days = models.IntegerField(
        default=3,
        help_text='Days after rent due date before penalty applies.',
    )
    effective_from = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'penalty_rules'
        verbose_name = 'Penalty Rule'

    def __str__(self):
        target = f"Unit {self.unit}" if self.unit else f"Property {self.property}"
        return f"{target}: {self.penalty_type} {self.penalty_value}"

    @builtins.property
    def is_unit_override(self):
        return self.unit_id is not None
