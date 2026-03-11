from rest_framework import serializers
from .models import Lease, LEASE_STATUS_CHOICES


class LeaseSerializer(serializers.ModelSerializer):
    """Full read + write serializer for leases."""
    status_display   = serializers.CharField(source="get_status_display", read_only=True)
    days_remaining   = serializers.IntegerField(read_only=True)
    is_expiring_soon = serializers.BooleanField(read_only=True)
    tenant_name      = serializers.CharField(source="tenant.user.full_name", read_only=True)
    unit_number      = serializers.CharField(source="unit.unit_number",      read_only=True)
    property_name    = serializers.CharField(source="unit.property.name",    read_only=True)

    class Meta:
        model  = Lease
        fields = [
            "id", "tenant", "tenant_name", "unit", "unit_number", "property_name",
            "lease_start", "lease_end", "monthly_rent", "deposit_amount",
            "rent_due_day", "grace_period_days",
            "status", "status_display",
            "tenant_signed_at", "lease_document_url",
            "days_remaining", "is_expiring_soon",
            "previous_lease", "created_at",
        ]
        read_only_fields = [
            "id", "tenant_name", "unit_number", "property_name",
            "status_display", "days_remaining", "is_expiring_soon",
            "tenant_signed_at", "lease_document_url",
            "previous_lease", "created_at",
        ]

    def validate_rent_due_day(self, value):
        if not (1 <= value <= 28):
            raise serializers.ValidationError(
                "rent_due_day must be between 1 and 28 (avoids month-end issues)."
            )
        return value

    def validate(self, attrs):
        if attrs.get("lease_end") and attrs.get("lease_start"):
            if attrs["lease_end"] <= attrs["lease_start"]:
                raise serializers.ValidationError(
                    {"lease_end": "Lease end date must be after start date."}
                )
        return attrs


class LeaseCreateSerializer(serializers.Serializer):
    """Used inside the tenant creation flow — not a standalone endpoint."""
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


class LeaseRenewSerializer(serializers.Serializer):
    new_end_date      = serializers.DateField()
    new_monthly_rent  = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False,
    )
