from rest_framework import serializers
from .models import SubscriptionPlan, Subscription


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'slug', 'plan_type', 'monthly_price', 'annual_price',
            'max_units', 'max_properties', 'sms_quota', 'features', 'is_active'
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    is_active = serializers.BooleanField(source='is_active', read_only=True)
    sms_remaining = serializers.IntegerField(source='get_sms_remaining', read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id', 'plan', 'status', 'billing_cycle',
            'trial_start', 'trial_end',
            'current_period_start', 'current_period_end',
            'sms_used_this_month', 'sms_reset_date', 'sms_remaining',
            'is_active'
        ]
