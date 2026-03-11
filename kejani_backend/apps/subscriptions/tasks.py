import logging
from celery import shared_task
from django.utils import timezone
from .models import Subscription

logger = logging.getLogger(__name__)


@shared_task
def expire_trials():
    """
    Finds all Subscriptions where:
      - status = 'trial'
      - trial_end is strictly in the past
    Updates them to 'expired'.
    """
    now = timezone.now()
    expired_count = Subscription.objects.filter(
        status='trial',
        trial_end__lt=now
    ).update(status='expired')
    
    if expired_count > 0:
        logger.info(f"Expired {expired_count} trial subscriptions.")
    return expired_count


@shared_task
def reset_sms_quotas():
    """
    Finds Subscriptions that need SMS quota resetting (usually monthly).
    In this simplified example, it runs on the 1st of the month,
    but can be expanded to run daily and check specific billing cycle thresholds depending on
    the `billing_cycle` field and `current_period_end`.
    For now, simply resets everyone's count and logs it.
    """
    today = timezone.now().date()
    
    reset_count = Subscription.objects.update(
        sms_used_this_month=0,
        sms_reset_date=today
    )
    
    if reset_count > 0:
        logger.info(f"Reset SMS quotas for {reset_count} active subscriptions.")
    return reset_count
