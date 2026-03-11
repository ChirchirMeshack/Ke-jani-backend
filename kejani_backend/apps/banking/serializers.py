from rest_framework import serializers
from .models import MpesaAccount, BankAccount
from .services import validate_mpesa_number


class MpesaAccountSerializer(serializers.ModelSerializer):
    """
    Used for both read (list/retrieve) and write (create).
    is_primary is read-only — the service layer sets it, not the client.
    """
    class Meta:
        model = MpesaAccount
        fields = [
            'id', 'account_type', 'till_number', 'paybill_number',
            'account_number', 'account_name', 'is_primary',
            'is_verified', 'created_at',
        ]
        read_only_fields = ['id', 'is_primary', 'is_verified', 'created_at']

    def validate(self, attrs):
        errors = validate_mpesa_number(
            account_type=attrs.get('account_type', 'till'),
            till_number=attrs.get('till_number', ''),
            paybill_number=attrs.get('paybill_number', ''),
        )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class BankAccountSerializer(serializers.ModelSerializer):
    bank_name_display = serializers.CharField(
        source='get_bank_name_display', read_only=True,
    )
    # Enforce max_length at serializer level (model has it too, belt-and-braces)
    account_number = serializers.CharField(max_length=30)

    class Meta:
        model = BankAccount
        fields = [
            'id', 'bank_name', 'bank_name_display', 'account_name',
            'account_number', 'branch', 'is_primary', 'created_at',
        ]
        read_only_fields = ['id', 'bank_name_display', 'is_primary', 'created_at']
