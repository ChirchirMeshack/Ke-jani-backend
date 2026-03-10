import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .managers import ActiveUserManager, AllUsersManager


class User(AbstractUser):
    """
    Custom user model for KE-JANI platform.
    Uses email as the login identifier. Never expose internal `id` — use `uuid`.
    """

    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('landlord', 'Landlord'),
        ('property_manager', 'Property Manager'),
        ('tenant', 'Tenant'),
    )

    APPROVAL_STATUS_CHOICES = (
        ('not_required', 'Not Required'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    )

    # ── Public identifier ─────────────────────────────────────────
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # ── Core fields ───────────────────────────────────────────────
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, blank=True)
    phone_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)

    # ── Role & status ─────────────────────────────────────────────
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default='not_required',
    )

    # ── Flags ─────────────────────────────────────────────────────
    is_first_login = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False)

    # ── Security ──────────────────────────────────────────────────
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    # ── Soft delete ───────────────────────────────────────────────
    deleted_at = models.DateTimeField(null=True, blank=True)

    # ── Timestamps ────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Managers ──────────────────────────────────────────────────
    objects = ActiveUserManager()
    objects_all = AllUsersManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} ({self.role})'

    # ── Methods ───────────────────────────────────────────────────

    def soft_delete(self):
        """Soft-delete: set deleted_at and deactivate."""
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save(update_fields=['deleted_at', 'is_active', 'updated_at'])

    @property
    def is_approved(self):
        return self.approval_status == 'approved'

    @property
    def full_name(self):
        return self.get_full_name()

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_landlord(self):
        return self.role == 'landlord'

    @property
    def is_property_manager(self):
        return self.role == 'property_manager'

    @property
    def is_tenant(self):
        return self.role == 'tenant'


class EmailVerificationToken(models.Model):
    """One-time email verification token for landlords and PMs."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='email_verification_token',
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = 'email_verification_tokens'

    def __str__(self):
        return f'EmailVerification for {self.user.email}'


class PasswordResetToken(models.Model):
    """
    Password reset token. FK (not OneToOne) because multiple resets can
    be requested — only the latest is valid.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='password_reset_tokens',
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'password_reset_tokens'

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(hours=1)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.is_used and self.expires_at > timezone.now()

    def __str__(self):
        return f'PasswordReset for {self.user.email}'


class PMInvitation(models.Model):
    """
    Created when a landlord invites a new PM to manage their property.
    """

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('expired', 'Expired'),
        ('declined', 'Declined'),
    )

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pm_invitations_sent',
    )
    property_id = models.IntegerField(null=True, blank=True)
    invite_token = models.UUIDField(default=uuid.uuid4, unique=True)
    invited_email = models.EmailField()
    invited_name = models.CharField(max_length=200)
    invited_phone = models.CharField(max_length=15, blank=True)
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.0
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
    expires_at = models.DateTimeField()
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='pm_invitations_received',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pm_invitations'

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)

    def is_valid(self):
        return self.status == 'pending' and self.expires_at > timezone.now()

    def __str__(self):
        return f'PMInvitation for {self.invited_email} by {self.invited_by.email}'


class TenantInvitation(models.Model):
    """
    Created when a landlord / PM invites a tenant to register
    for a specific unit.
    """

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('expired', 'Expired'),
    )

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tenant_invitations_sent',
    )
    unit_id = models.IntegerField(null=True, blank=True)
    unit_number = models.CharField(max_length=20, blank=True)
    property_name = models.CharField(max_length=200, blank=True)
    invite_token = models.UUIDField(default=uuid.uuid4, unique=True)
    invited_email = models.EmailField()
    invited_name = models.CharField(max_length=200, blank=True)
    invited_phone = models.CharField(max_length=15, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
    expires_at = models.DateTimeField()
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='tenant_invitations_received',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tenant_invitations'

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)

    def is_valid(self):
        return self.status == 'pending' and self.expires_at > timezone.now()

    def __str__(self):
        return f'TenantInvitation for {self.invited_email}'


class AccessAuditLog(models.Model):
    """
    Immutable audit log — insert only, never update/delete.
    DB-level rules enforced via migration RunSQL.
    """

    EVENT_CHOICES = (
        ('login_success', 'Login Success'),
        ('login_failed', 'Login Failed'),
        ('logout', 'Logout'),
        ('registration', 'Registration'),
        ('email_verified', 'Email Verified'),
        ('password_reset_requested', 'Password Reset Requested'),
        ('password_reset_completed', 'Password Reset Completed'),
        ('password_changed', 'Password Changed'),
        ('account_approved', 'Account Approved'),
        ('account_rejected', 'Account Rejected'),
        ('account_suspended', 'Account Suspended'),
        ('demo_login', 'Demo Login'),
        ('invitation_sent', 'Invitation Sent'),
        ('invitation_accepted', 'Invitation Accepted'),
    )

    event = models.CharField(max_length=30, choices=EVENT_CHOICES)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_logs',
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    role = models.CharField(max_length=20, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'access_audit_log'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.event} — {self.user or "anonymous"} — {self.created_at}'
