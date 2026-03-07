from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin


class User(AbstractBaseUser, PermissionsMixin):

    ROLE_CHOICES = (
        ("admin", "Admin"),
        ("project_manager", "Project Manager"),
        ("landlord", "Landlord"),
        ("tenant", "Tenant"),
    )

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    username = models.CharField(max_length=50, unique=True)
    email = models.EmailField(unique=True)

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    phone = models.CharField(max_length=20, blank=True)

    created_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    approved_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_users"
    )

    approved_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return f"{self.username} ({self.role})"






class Property(models.Model):

    name = models.CharField(max_length=200)

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="properties"
    )

    address = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)






class Unit(models.Model):

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="units"
    )

    unit_number = models.CharField(max_length=20)

    rent = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )







class Tenant(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE
    )

    unit = models.ForeignKey(
        Unit,
        on_delete=models.SET_NULL,
        null=True,
        related_name="tenants"
    )

    emergency_contact = models.CharField(max_length=100)

    move_in_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)








