import uuid
from django.contrib.auth.models import BaseUserManager
from django.db import models


class ActiveUserManager(BaseUserManager):
    """
    Custom manager that filters out soft-deleted users by default.
    Also handles user/superuser creation with email as the identifier.
    """

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        # Auto-generate unique username if not provided
        if 'username' not in extra_fields or not extra_fields['username']:
            extra_fields['username'] = uuid.uuid4().hex[:30]
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('approval_status', 'not_required')
        extra_fields.setdefault('email_verified', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class AllUsersManager(models.Manager):
    """Unfiltered manager — includes soft-deleted users. For admin use."""
    pass
