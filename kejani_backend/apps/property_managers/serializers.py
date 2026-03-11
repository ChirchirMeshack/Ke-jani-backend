from rest_framework import serializers
from .models import (
    PropertyManager, PmServiceArea, PmAssignmentRequest, CommissionRecord,
)
from .services import validate_cloudinary_url


# ── PM Profile ────────────────────────────────────────────────────────

class PmProfileSerializer(serializers.ModelSerializer):
    """Full read serializer — returned for GET /api/property-managers/profile/"""
    full_name               = serializers.CharField(source="user.full_name",  read_only=True)
    email                   = serializers.EmailField(source="user.email",     read_only=True)
    phone                   = serializers.CharField(source="user.phone",      read_only=True)
    uuid                    = serializers.UUIDField(source="user.uuid",       read_only=True)
    approval_status_display = serializers.CharField(source="get_approval_status_display", read_only=True)
    onboarding_progress     = serializers.DictField(read_only=True)
    total_units_managed     = serializers.IntegerField(read_only=True)
    service_areas           = serializers.SerializerMethodField()

    def get_service_areas(self, obj):
        return list(obj.service_areas.values("id", "county", "area"))

    class Meta:
        model  = PropertyManager
        fields = [
            "id", "uuid", "full_name", "email", "phone",
            "id_number", "company_name", "bio", "is_searchable",
            "id_copy_front_url", "id_copy_back_url",
            "commission_rate", "subscription_tier", "subscription_active",
            "approval_status", "approval_status_display",
            "onboarding_progress",
            "total_units_managed",
            "service_areas",
            "created_at",
        ]
        read_only_fields = fields


class PmProfileUpdateSerializer(serializers.ModelSerializer):
    """PATCH — updates allowed PM profile fields."""
    id_copy_front_url = serializers.URLField(required=False, allow_blank=True)
    id_copy_back_url  = serializers.URLField(required=False, allow_blank=True)

    class Meta:
        model  = PropertyManager
        fields = [
            "id_number", "company_name", "bio",
            "commission_rate",
            "id_copy_front_url", "id_copy_back_url",
        ]

    def validate_id_copy_front_url(self, value):
        if value and not validate_cloudinary_url(value, self.context["request"].user):
            raise serializers.ValidationError("Invalid file URL.")
        return value

    def validate_id_copy_back_url(self, value):
        if value and not validate_cloudinary_url(value, self.context["request"].user):
            raise serializers.ValidationError("Invalid file URL.")
        return value


# ── PM Public Profile (shown to landlords in search) ──────────────────

class PmPublicProfileSerializer(serializers.ModelSerializer):
    """Read-only. Shown to landlords searching for a PM to hire."""
    full_name           = serializers.CharField(source="user.full_name", read_only=True)
    total_units_managed = serializers.IntegerField(read_only=True)
    service_areas       = serializers.SerializerMethodField()

    def get_service_areas(self, obj):
        return list(obj.service_areas.values("id", "county", "area"))

    class Meta:
        model  = PropertyManager
        fields = [
            "id", "full_name", "bio", "company_name",
            "commission_rate", "total_units_managed",
            "service_areas",
        ]
        read_only_fields = fields


# ── Service Areas ─────────────────────────────────────────────────────

class PmServiceAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PmServiceArea
        fields = ["id", "county", "area", "created_at"]
        read_only_fields = ["id", "created_at"]


# ── Assignment Requests ───────────────────────────────────────────────

class PmAssignmentRequestSerializer(serializers.ModelSerializer):
    """Full read + write for assignment requests."""
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    property_name  = serializers.CharField(source="property.name",           read_only=True)
    landlord_name  = serializers.CharField(source="landlord.user.full_name", read_only=True)
    pm_name        = serializers.SerializerMethodField()

    def get_pm_name(self, obj):
        return obj.pm.user.full_name if obj.pm else ""

    class Meta:
        model  = PmAssignmentRequest
        fields = [
            "id", "landlord", "landlord_name", "pm", "pm_name",
            "property", "property_name",
            "commission_rate", "can_add_tenants", "can_handle_maintenance",
            "expense_approval_threshold", "proposed_start_date",
            "status", "status_display", "decline_reason",
            "invite_email", "invite_name",
            "responded_at", "created_at",
        ]
        read_only_fields = [
            "id", "landlord", "landlord_name", "pm_name", "property_name",
            "status_display", "responded_at", "created_at",
        ]


class AssignExistingPmSerializer(serializers.Serializer):
    """POST /api/property-managers/assign/"""
    property_id                = serializers.IntegerField()
    pm_id                      = serializers.IntegerField()
    commission_rate            = serializers.DecimalField(max_digits=5, decimal_places=2, default=10)
    can_add_tenants            = serializers.BooleanField(default=True)
    can_handle_maintenance     = serializers.BooleanField(default=True)
    expense_approval_threshold = serializers.DecimalField(max_digits=10, decimal_places=2, default=10000)
    proposed_start_date        = serializers.DateField(required=False, allow_null=True)


class InviteNewPmSerializer(serializers.Serializer):
    """POST /api/property-managers/invite/"""
    property_id                = serializers.IntegerField()
    email                      = serializers.EmailField()
    name                       = serializers.CharField(max_length=200)
    phone                      = serializers.CharField(max_length=15, required=False, default="")
    commission_rate            = serializers.DecimalField(max_digits=5, decimal_places=2, default=10)
    can_add_tenants            = serializers.BooleanField(default=True)
    can_handle_maintenance     = serializers.BooleanField(default=True)
    expense_approval_threshold = serializers.DecimalField(max_digits=10, decimal_places=2, default=10000)


class AcceptPmInviteSerializer(serializers.Serializer):
    """POST /api/property-managers/invite/accept/"""
    token      = serializers.CharField(max_length=64)
    first_name = serializers.CharField(max_length=150)
    last_name  = serializers.CharField(max_length=150)
    email      = serializers.EmailField()
    phone      = serializers.CharField(max_length=15, required=False, default="")
    password   = serializers.CharField(min_length=8, write_only=True)


class AssignmentRespondSerializer(serializers.Serializer):
    """POST .../accept/ or .../decline/"""
    reason = serializers.CharField(required=False, allow_blank=True, default="")


# ── Commission Records ────────────────────────────────────────────────

class CommissionRecordSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    property_name  = serializers.CharField(source="property.name",     read_only=True)
    pm_name        = serializers.CharField(source="pm.user.full_name", read_only=True)

    class Meta:
        model  = CommissionRecord
        fields = [
            "id", "pm", "pm_name", "property", "property_name",
            "payment_id",
            "rent_amount", "commission_rate", "commission_amount",
            "period", "status", "status_display",
            "paid_at", "payment_notes",
            "created_at",
        ]
        read_only_fields = [
            "id", "pm_name", "property_name", "status_display", "created_at",
            "commission_amount",
        ]
