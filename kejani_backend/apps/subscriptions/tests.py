from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse

from apps.subscriptions.models import SubscriptionPlan, Subscription
from apps.subscriptions.services import create_trial_subscription, sync_subscription_tier_to_profile
from apps.subscriptions.tasks import expire_trials, reset_sms_quotas
from apps.landlords.models import Landlord
from apps.property_managers.models import PropertyManager
from apps.subscriptions.exceptions import SubscriptionLimitError
from django.conf import settings

User = get_user_model()


class SubscriptionModelsTests(TestCase):
    def setUp(self):
        # The DB already seeded the plans via the migration 0002_seed_plans.py
        # We can just fetch them
        self.solo_plan = SubscriptionPlan.objects.get(slug='solo')
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass',
            role='landlord'
        )

    def test_subscription_creation_and_properties(self):
        now = timezone.now()
        trial_end = now + timedelta(days=30)
        sub = Subscription.objects.create(
            user=self.user,
            plan=self.solo_plan,
            status='trial',
            trial_end=trial_end
        )
        self.assertTrue(sub.is_active())
        self.assertEqual(sub.get_feature_limit('max_units'), 10)
        self.assertEqual(sub.get_feature_limit('max_properties'), 2)
        self.assertTrue(sub.has_feature('mpesa_collection'))
        self.assertFalse(sub.has_feature('api_access'))
        self.assertEqual(sub.get_sms_remaining(), 50)
        
        # Test expiration
        sub.trial_end = now - timedelta(days=1)
        sub.save()
        self.assertFalse(sub.is_active())


class SubscriptionServicesTests(TestCase):
    def setUp(self):
        self.user_ll = User.objects.create_user(
            email='ll@example.com', password='pass', role='landlord'
        )
        self.ll_profile = Landlord.objects.create(user=self.user_ll)
        
        self.user_pm = User.objects.create_user(
            email='pm@example.com', password='pass', role='property_manager'
        )
        self.pm_profile = PropertyManager.objects.create(user=self.user_pm)

    def test_create_trial_subscription_landlord(self):
        sub = create_trial_subscription(self.user_ll, 'starter')
        self.assertEqual(sub.plan.slug, 'starter')
        self.assertEqual(sub.status, 'trial')
        self.assertIsNotNone(sub.trial_end)
        
        # Verify sync to profile
        self.ll_profile.refresh_from_db()
        self.assertEqual(self.ll_profile.subscription_tier, 'starter')

    def test_create_trial_subscription_pm(self):
        sub = create_trial_subscription(self.user_pm, 'starter_pm')
        self.assertEqual(sub.plan.slug, 'starter_pm')
        self.assertEqual(sub.status, 'trial')
        
        # Verify sync to profile
        self.pm_profile.refresh_from_db()
        self.assertEqual(self.pm_profile.subscription_tier, 'starter_pm')

    def test_create_trial_subscription_fallback(self):
        # Give a non-existent slug
        sub = create_trial_subscription(self.user_ll, 'invalid_slug')
        self.assertEqual(sub.plan.slug, 'solo')  # Fallback for landlord


class SubscriptionTasksTests(TestCase):
    def setUp(self):
        self.plan = SubscriptionPlan.objects.get(slug='solo')
        self.user1 = User.objects.create_user(email='user1@example.com', password='p')
        self.user2 = User.objects.create_user(email='user2@example.com', password='p')
        self.user3 = User.objects.create_user(email='user3@example.com', password='p')

    def test_expire_trials(self):
        now = timezone.now()
        # Active trial
        Subscription.objects.create(user=self.user1, plan=self.plan, status='trial', trial_end=now + timedelta(days=10))
        # Expired trial
        Subscription.objects.create(user=self.user2, plan=self.plan, status='trial', trial_end=now - timedelta(days=1))
        # Active non-trial
        Subscription.objects.create(user=self.user3, plan=self.plan, status='active', trial_end=now - timedelta(days=1))

        expired_count = expire_trials()
        self.assertEqual(expired_count, 1)

        self.assertEqual(Subscription.objects.get(user=self.user2).status, 'expired')
        self.assertEqual(Subscription.objects.get(user=self.user1).status, 'trial')
        self.assertEqual(Subscription.objects.get(user=self.user3).status, 'active')

    def test_reset_sms_quotas(self):
        Subscription.objects.create(user=self.user1, plan=self.plan, sms_used_this_month=25)
        Subscription.objects.create(user=self.user2, plan=self.plan, sms_used_this_month=10)
        
        reset_sms_quotas()
        
        self.user1.subscription.refresh_from_db()
        self.assertEqual(self.user1.subscription.sms_used_this_month, 0)


class SubscriptionViewsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email='test@example.com', password='pass')
        self.client.force_authenticate(user=self.user)
        self.plan = SubscriptionPlan.objects.get(slug='solo')

    def test_get_my_subscription_no_sub(self):
        url = reverse('subscriptions:my-subscription')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_my_subscription(self):
        create_trial_subscription(self.user, 'solo')
        url = reverse('subscriptions:my-subscription')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['plan']['slug'], 'solo')
        self.assertTrue(response.data['is_active'])

    def test_get_available_plans(self):
        url = reverse('subscriptions:available-plans')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 5 landlord plans + 3 PM plans = 8
        self.assertEqual(len(response.data), 8)

    def test_get_available_plans_filtered(self):
        url = reverse('subscriptions:available-plans') + "?type=property_manager"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)
