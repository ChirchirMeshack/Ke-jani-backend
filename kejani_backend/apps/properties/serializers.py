from rest_framework import serializers
from .models import (
    Property, Unit, PropertyAmenity, PropertyPhoto, PenaltyRule,
    AMENITY_CHOICES, PROPERTY_TYPE_CHOICES, LISTING_TYPE_CHOICES,
    UNIT_STATUS_CHOICES, PENALTY_TYPE_CHOICES, KENYA_COUNTIES,
)
from .services import validate_cloudinary_url


# ── PenaltyRule ──────────────────────────────────────────────────────

class PenaltyRuleSerializer(serializers.ModelSerializer):
    penalty_type_display = serializers.CharField(
        source="get_penalty_type_display", read_only=True,
    )
    class Meta:
        model  = PenaltyRule
        fields = [
            "id", "penalty_type", "penalty_type_display",
            "penalty_value", "grace_period_days",
            "effective_from", "is_unit_override",
        ]
        read_only_fields = ["id", "penalty_type_display", "is_unit_override"]


# ── PropertyAmenity ──────────────────────────────────────────────────

class PropertyAmenitySerializer(serializers.ModelSerializer):
    amenity_label = serializers.CharField(
        source="get_amenity_name_display", read_only=True,
    )
    class Meta:
        model  = PropertyAmenity
        fields = ["amenity_name", "amenity_label", "available"]
        read_only_fields = ["amenity_label"]


class AmenitiesBulkSerializer(serializers.Serializer):
    """
    Accepts a flat dict of all 10 amenity keys.
    Used for PUT /api/properties/<id>/amenities/
    All keys are optional — missing keys default to False.
    """
    swimming_pool    = serializers.BooleanField(required=False, default=False)
    gym              = serializers.BooleanField(required=False, default=False)
    backup_generator = serializers.BooleanField(required=False, default=False)
    security_24hr    = serializers.BooleanField(required=False, default=False)
    cctv             = serializers.BooleanField(required=False, default=False)
    parking          = serializers.BooleanField(required=False, default=False)
    elevator         = serializers.BooleanField(required=False, default=False)
    wifi             = serializers.BooleanField(required=False, default=False)
    playground       = serializers.BooleanField(required=False, default=False)
    pet_friendly     = serializers.BooleanField(required=False, default=False)

    def to_amenity_dict(self):
        """Maps field names to AMENITY_CHOICES keys for set_amenities()."""
        d = self.validated_data
        return {
            "swimming_pool":    d.get("swimming_pool",    False),
            "gym":              d.get("gym",              False),
            "backup_generator": d.get("backup_generator", False),
            "24hr_security":    d.get("security_24hr",   False),
            "cctv":             d.get("cctv",             False),
            "parking":          d.get("parking",          False),
            "elevator":         d.get("elevator",         False),
            "wifi":             d.get("wifi",             False),
            "playground":       d.get("playground",       False),
            "pet_friendly":     d.get("pet_friendly",     False),
        }


# ── PropertyPhoto ─────────────────────────────────────────────────────

class PropertyPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PropertyPhoto
        fields = [
            "id", "photo_url", "cloudinary_id",
            "display_order", "unit",
        ]
        read_only_fields = ["id", "display_order"]

    def validate_photo_url(self, value):
        user = self.context["request"].user
        if not validate_cloudinary_url(value, user):
            raise serializers.ValidationError(
                "Invalid photo URL. Upload via the KE-JANI system."
            )
        return value


class PhotoReorderSerializer(serializers.Serializer):
    """Accepts ordered list of photo IDs for drag-and-drop reorder."""
    ordered_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
    )


# ── Unit ─────────────────────────────────────────────────────────────

class UnitSerializer(serializers.ModelSerializer):
    status_display       = serializers.CharField(source="get_status_display", read_only=True)
    effective_penalty    = PenaltyRuleSerializer(source="effective_penalty_rule", read_only=True)

    class Meta:
        model  = Unit
        fields = [
            "id", "unit_number", "bedrooms", "bathrooms",
            "size_sqft", "floor_level", "furnished", "has_parking",
            "rent_amount", "sale_price", "deposit_amount",
            "status", "status_display",
            "effective_penalty",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status_display", "effective_penalty", "created_at", "updated_at"]

    def validate_unit_number(self, value):
        """Ensure unit_number is unique within this property."""
        request = self.context.get("request")
        property_id = self.context.get("property_id")
        if not property_id:
            return value
        qs = Unit.objects.filter(property_id=property_id, unit_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Unit number '{value}' already exists in this property."
            )
        return value


# ── Property ─────────────────────────────────────────────────────────

class PropertyListSerializer(serializers.ModelSerializer):
    """Compact serializer for the property list view."""
    county_display       = serializers.CharField(source="get_county_display",       read_only=True)
    property_type_display= serializers.CharField(source="get_property_type_display",read_only=True)
    listing_type_display = serializers.CharField(source="get_listing_type_display", read_only=True)
    occupancy_percent    = serializers.IntegerField(read_only=True)
    setup_gap            = serializers.IntegerField(read_only=True)
    cover_photo          = serializers.SerializerMethodField()

    def get_cover_photo(self, obj):
        """Returns the first photo URL (display_order=0) or None."""
        photo = obj.photos.order_by("display_order").first()
        return photo.photo_url if photo else None

    class Meta:
        model  = Property
        fields = [
            "id", "name", "property_type", "property_type_display",
            "listing_type", "listing_type_display",
            "county", "county_display", "area", "estate",
            "declared_units", "actual_units",
            "occupancy_percent", "setup_gap",
            "is_active", "management_mode",
            "cover_photo", "created_at",
        ]
        read_only_fields = fields


class PropertyDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer — used for GET /api/properties/<id>/"""
    county_display        = serializers.CharField(source="get_county_display",        read_only=True)
    property_type_display = serializers.CharField(source="get_property_type_display", read_only=True)
    listing_type_display  = serializers.CharField(source="get_listing_type_display",  read_only=True)
    occupancy_percent     = serializers.IntegerField(read_only=True)
    setup_gap             = serializers.IntegerField(read_only=True)
    amenities = PropertyAmenitySerializer(many=True, read_only=True)
    photos    = PropertyPhotoSerializer(many=True,   read_only=True)
    units     = UnitSerializer(many=True,            read_only=True)

    class Meta:
        model  = Property
        fields = [
            "id", "name", "property_type", "property_type_display",
            "listing_type", "listing_type_display",
            "description",
            "county", "county_display", "area", "estate",
            "street_address", "latitude", "longitude",
            "declared_units", "actual_units",
            "occupancy_percent", "setup_gap",
            "management_mode", "pm_assigned_at",
            "is_active",
            "amenities", "photos", "units",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class PropertyCreateSerializer(serializers.ModelSerializer):
    """Used for POST /api/properties/ — create a new property."""
    class Meta:
        model  = Property
        fields = [
            "name", "property_type", "listing_type",
            "description",
            "county", "area", "estate",
            "street_address", "latitude", "longitude",
            "declared_units",
        ]

    def validate_declared_units(self, value):
        if value < 1:
            raise serializers.ValidationError("A property must have at least 1 unit.")
        return value


class PropertyUpdateSerializer(serializers.ModelSerializer):
    """Used for PATCH /api/properties/<id>/ — all fields optional."""
    class Meta:
        model  = Property
        fields = [
            "name", "property_type", "listing_type",
            "description",
            "county", "area", "estate",
            "street_address", "latitude", "longitude",
            "declared_units", "is_active",
        ]
