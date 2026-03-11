from rest_framework import serializers
from .models import Landlord, ESTIMATED_UNITS_CHOICES, SUBSCRIPTION_TIER_CHOICES
from .services import validate_cloudinary_url
from apps.banking.serializers import MpesaAccountSerializer, BankAccountSerializer


class LandlordProfileSerializer(serializers.ModelSerializer):
    """
    Full read serializer — returned by GET /api/landlords/profile/
    Frontend uses this on every load to know what to show in the wizard
    and which features to display based on subscription_tier.
    """
    full_name    = serializers.CharField(source='user.full_name',  read_only=True)
    email        = serializers.EmailField(source='user.email',     read_only=True)
    phone        = serializers.CharField(source='user.phone',      read_only=True)
    uuid         = serializers.UUIDField(source='user.uuid',       read_only=True)
    recommended_tier     = serializers.CharField(read_only=True)
    onboarding_progress  = serializers.DictField(read_only=True)
    is_profile_complete  = serializers.BooleanField(read_only=True)

    # SerializerMethodField avoids the RelatedManager TypeError from v1.
    # Each method queries only the primary account — one extra DB query each
    # (prevented by prefetch_related in get_landlord_or_404).
    primary_mpesa = serializers.SerializerMethodField()
    primary_bank  = serializers.SerializerMethodField()

    def get_primary_mpesa(self, obj):
        account = obj.user.mpesa_accounts.filter(is_primary=True).first()
        return MpesaAccountSerializer(account).data if account else None

    def get_primary_bank(self, obj):
        account = obj.user.bank_accounts.filter(is_primary=True).first()
        return BankAccountSerializer(account).data if account else None

    class Meta:
        model  = Landlord
        fields = [
            'uuid', 'full_name', 'email', 'phone',
            'id_number', 'estimated_units_range',
            'avatar_url', 'id_copy_front_url', 'id_copy_back_url',
            'subscription_tier', 'recommended_tier',
            'approved_at', 'terms_accepted_at',
            'onboarding_progress', 'is_profile_complete',
            'primary_mpesa', 'primary_bank',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class LandlordProfileStepSerializer(serializers.Serializer):
    """
    Handles Step 1 of the 5-step onboarding wizard.
    All Cloudinary URLs are validated against the current user's UUID.
    """
    # Optional — landlord may skip avatar
    avatar_url        = serializers.URLField(required=False, allow_blank=True)

    # Required to complete Step 1
    id_copy_front_url = serializers.URLField(required=True)
    id_copy_back_url  = serializers.URLField(required=True)

    # Editable — pre-filled from registration, landlord can correct typos
    id_number         = serializers.CharField(max_length=20, required=False)

    # Required — landlord confirms tier (pre-selected from estimated_units_range)
    subscription_tier = serializers.ChoiceField(choices=SUBSCRIPTION_TIER_CHOICES, required=True)

    # Required — KDPA 2019 compliance
    terms_agreed      = serializers.BooleanField(required=True)

    def validate_terms_agreed(self, value):
        if not value:
            raise serializers.ValidationError(
                'You must accept the Terms of Service to continue.'
            )
        return value

    def _validate_url_field(self, url, field_name):
        """Helper: validates Cloudinary URL with user UUID check."""
        user = self.context['request'].user
        if url and not validate_cloudinary_url(url, user):
            raise serializers.ValidationError(
                f'{field_name}: Invalid URL. Upload via the KE-JANI system only.'
            )
        return url

    def validate_id_copy_front_url(self, value):
        return self._validate_url_field(value, 'id_copy_front_url')

    def validate_id_copy_back_url(self, value):
        return self._validate_url_field(value, 'id_copy_back_url')

    def validate_avatar_url(self, value):
        return self._validate_url_field(value, 'avatar_url') if value else value


class LandlordBasicUpdateSerializer(serializers.Serializer):
    """Updates basic profile info from the Settings page (post-onboarding)."""
    first_name = serializers.CharField(max_length=150, required=False)
    last_name  = serializers.CharField(max_length=150, required=False)
    phone      = serializers.CharField(max_length=15,  required=False)
    avatar_url = serializers.URLField(required=False, allow_blank=True)

    def validate_avatar_url(self, value):
        user = self.context['request'].user
        if value and not validate_cloudinary_url(value, user):
            raise serializers.ValidationError('Invalid file URL.')
        return value


class AdminLandlordListSerializer(serializers.ModelSerializer):
    """Read-only serializer for admin landlord review screen."""
    full_name         = serializers.CharField(source='user.full_name',       read_only=True)
    email             = serializers.EmailField(source='user.email',          read_only=True)
    phone             = serializers.CharField(source='user.phone',           read_only=True)
    approval_status   = serializers.CharField(source='user.approval_status', read_only=True)
    is_profile_complete = serializers.BooleanField(read_only=True)
    approved_by_name  = serializers.SerializerMethodField()

    def get_approved_by_name(self, obj):
        return obj.approved_by.full_name if obj.approved_by else None

    class Meta:
        model  = Landlord
        fields = [
            'id', 'full_name', 'email', 'phone',
            'id_number', 'estimated_units_range',
            'subscription_tier', 'approval_status',
            'id_copy_front_url', 'id_copy_back_url',
            'is_profile_complete',
            'approved_by_name', 'approved_at',
            'onboarding_step_profile_completed',
            'onboarding_step_mpesa_completed',
            'onboarding_completed_at',
            'created_at',
        ]
        read_only_fields = fields
