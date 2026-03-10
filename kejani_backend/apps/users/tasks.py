"""
Celery task stubs for the users app.
"""
from celery import shared_task
from django.utils import timezone


@shared_task(name='users.reset_demo_account')
def reset_demo_account():
    """
    Runs daily at midnight EAT.
    Resets demo user's profile fields back to original state.
    Will be extended to reset demo properties/payments/tickets
    once those apps exist.
    """
    from apps.users.models import User

    try:
        demo_user = User.objects.get(email='demo@ke-jani.com', is_demo=True)
        demo_user.first_name = 'Demo'
        demo_user.last_name = 'Landlord'
        demo_user.phone = '+254700000000'
        demo_user.save(
            update_fields=['first_name', 'last_name', 'phone', 'updated_at']
        )
    except User.DoesNotExist:
        pass


@shared_task(name='users.expire_old_invitations')
def expire_old_invitations():
    """
    Runs daily. Marks PMInvitation and TenantInvitation records
    as expired where expires_at < now() AND status == 'pending'.
    """
    from apps.users.models import PMInvitation, TenantInvitation

    now = timezone.now()

    pm_expired = PMInvitation.objects.filter(
        status='pending', expires_at__lt=now
    ).update(status='expired')

    tenant_expired = TenantInvitation.objects.filter(
        status='pending', expires_at__lt=now
    ).update(status='expired')

    return f'Expired {pm_expired} PM invitations, {tenant_expired} tenant invitations.'
