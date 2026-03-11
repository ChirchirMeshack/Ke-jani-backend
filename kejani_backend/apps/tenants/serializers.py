from rest_framework import serializers
from .models import Tenant
from .services import validate_cloudinary_url
from apps.leases.serializers import LeaseSerializer


class TenantProfileSerializer(serializers.ModelSerializer):
    """Full read serializer — returned for GET /api/tenants/<id>/"""
    full_name   = serializers.CharField(source="user.full_name",  read_only=True)
    email       = serializers.EmailField(source="user.email",     read_only=True)
    phone       = serializers.CharField(source="user.phone",      read_only=True)
    uuid        = serializers.UUIDField(source="user.uuid",       read_only=True)
    current_lease = serializers.SerializerMethodField()
    current_unit  = serializers.SerializerMethodField()

    def get_current_lease(self, obj):
        lease = obj.current_lease
        return LeaseSerializer(lease).data if lease else None

    def get_current_unit(self, obj):
        unit = obj.current_unit
        if not unit:
            return None
        return {
            "id":          unit.id,
            "unit_number": unit.unit_number,
            "property_id": unit.property_id,
            "property_name": unit.property.name,
            "rent_amount": str(unit.rent_amount),
        }

    class Meta:
        model  = Tenant
        fields = [
            "id", "uuid", "full_name", "email", "phone",
            "id_number", "phone_alt",
            "id_copy_front_url", "id_copy_back_url",
            "emergency_contact_name", "emergency_contact_phone",
            "emergency_contact_relationship",
            "employer_name", "employer_contact",
            "payment_preference", "notification_preference",
            "terms_accepted_at",
            "has_changed_password", "has_viewed_lease",
            "is_onboarding_complete",
            "current_lease", "current_unit",
            "created_at",
        ]
        read_only_fields = fields


class TenantCreateSerializer(serializers.Serializer):
    """
    Used for POST /api/tenants/ — creates user + tenant + lease in one call.
    Nested: user info + tenant info + lease terms all in one request body.
    """
    # ── User fields ───────────────────────────────────────────────
    first_name = serializers.CharField(max_length=150)
    last_name  = serializers.CharField(max_length=150)
    email      = serializers.EmailField()
    phone      = serializers.CharField(max_length=15)

    # ── Tenant fields ─────────────────────────────────────────────
    unit_id        = serializers.IntegerField()
    id_number      = serializers.CharField(max_length=20, required=False, default="")
    phone_alt      = serializers.CharField(max_length=15, required=False, default="")
    emergency_contact_name         = serializers.CharField(max_length=200, required=False, default="")
    emergency_contact_phone        = serializers.CharField(max_length=15,  required=False, default="")
    emergency_contact_relationship = serializers.CharField(max_length=100, required=False, default="")
    employer_name    = serializers.CharField(max_length=200, required=False, default="")
    employer_contact = serializers.CharField(max_length=100, required=False, default="")
    payment_preference = serializers.ChoiceField(
        choices=["mpesa", "bank"], default="mpesa",
    )

    # ── Lease fields ──────────────────────────────────────────────
    lease_start       = serializers.DateField()
    lease_end         = serializers.DateField()
    monthly_rent      = serializers.DecimalField(max_digits=12, decimal_places=2)
    deposit_amount    = serializers.DecimalField(max_digits=12, decimal_places=2)
    rent_due_day      = serializers.IntegerField(default=1, min_value=1, max_value=28)
    grace_period_days = serializers.IntegerField(default=3, min_value=0, max_value=30)

    def validate(self, attrs):
        if attrs["lease_end"] <= attrs["lease_start"]:
            raise serializers.ValidationError(
                {"lease_end": "Lease end must be after lease start."}
            )
        return attrs

    def split(self):
        """
        Splits validated_data into three separate dicts for create_tenant().
        Returns: (user_data, tenant_data, lease_data)
        """
        d = self.validated_data
        user_data = {
            "first_name": d["first_name"],
            "last_name":  d["last_name"],
            "email":      d["email"],
            "phone":      d["phone"],
        }
        tenant_data = {
            "id_number":   d.get("id_number", ""),
            "phone_alt":   d.get("phone_alt", ""),
            "emergency_contact_name":         d.get("emergency_contact_name", ""),
            "emergency_contact_phone":        d.get("emergency_contact_phone", ""),
            "emergency_contact_relationship": d.get("emergency_contact_relationship", ""),
            "employer_name":    d.get("employer_name", ""),
            "employer_contact": d.get("employer_contact", ""),
            "payment_preference": d.get("payment_preference", "mpesa"),
        }
        lease_data = {
            "lease_start":       d["lease_start"],
            "lease_end":         d["lease_end"],
            "monthly_rent":      d["monthly_rent"],
            "deposit_amount":    d["deposit_amount"],
            "rent_due_day":      d.get("rent_due_day", 1),
            "grace_period_days": d.get("grace_period_days", 3),
        }
        return user_data, tenant_data, lease_data


class TenantUpdateSerializer(serializers.ModelSerializer):
    """PATCH — updates allowed tenant profile fields."""
    id_copy_front_url = serializers.URLField(required=False, allow_blank=True)
    id_copy_back_url  = serializers.URLField(required=False, allow_blank=True)

    class Meta:
        model  = Tenant
        fields = [
            "id_number", "phone_alt",
            "emergency_contact_name", "emergency_contact_phone",
            "emergency_contact_relationship",
            "employer_name", "employer_contact",
            "payment_preference", "notification_preference",
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
