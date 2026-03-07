from django.core.mail import send_mail
from django.conf import settings



def send_landlord_approval_email(user):
    subject = "Landlord Account Approved"
    message = f"""
  Hello {user.username},

Your landlord account has been approved.
You can now access your dashboard.

Regards,
Management
"""

send_mail(subject, message, settings.DEFAULT_FROM_EMAIL,[user.email])
