"""
Management command to seed the demo landlord account.
Usage: python manage.py seed_demo
"""
from django.core.management.base import BaseCommand

from apps.users.models import User


class Command(BaseCommand):
    help = 'Create or verify the demo landlord account (demo@ke-jani.com)'

    def handle(self, *args, **options):
        email = 'demo@ke-jani.com'

        if User.objects_all.filter(email=email).exists():
            self.stdout.write(
                self.style.WARNING(
                    f'Demo user ({email}) already exists. Skipping.'
                )
            )
            return

        user = User.objects.create_user(
            email=email,
            password='DemoPassword123!',
            username='demo_landlord',
            first_name='Demo',
            last_name='Landlord',
            phone='+254700000000',
            role='landlord',
            approval_status='approved',
            email_verified=True,
            is_demo=True,
            is_first_login=False,
        )
        user.is_staff = False
        user.save(update_fields=['is_staff'])

        self.stdout.write(
            self.style.SUCCESS(
                f'Demo user created: {email} / DemoPassword123!'
            )
        )
