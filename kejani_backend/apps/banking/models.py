from django.db import models, transaction
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class ActiveManager(models.Manager):
    """Default manager — filters out soft-deleted records."""
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class MpesaAccount(models.Model):
    """
    Stores M-Pesa receiving details for landlords and PMs.

    Two types:
    - till:    6-digit till number. Tenant pays directly to till.
    - paybill: 6-digit paybill + account number. Tenant enters
               account_number as reference when paying.

    Only one account per user can be is_primary=True at a time.
    The save() method enforces this atomically.
    """
    ACCOUNT_TYPE_CHOICES = [
        ('till', 'Till Number'),
        ('paybill', 'Paybill Number'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mpesa_accounts',
        db_index=True,  # explicit per schema indexing guidelines
    )
    account_type = models.CharField(
        max_length=10,
        choices=ACCOUNT_TYPE_CHOICES,
        default='till',
    )
    till_number    = models.CharField(max_length=10, blank=True)
    paybill_number = models.CharField(max_length=10, blank=True)
    account_number = models.CharField(
        max_length=50, blank=True,
        help_text='Reference number tenants enter when paying via paybill.',
    )
    account_name   = models.CharField(
        max_length=100, blank=True,
        help_text='Friendly label shown in UI, e.g. "Equity Bank Paybill".',
    )
    is_primary  = models.BooleanField(default=False)
    is_verified = models.BooleanField(
        default=False,
        help_text='Set True after first successful payment received.',
    )

    # Soft delete — never physically remove payment method records
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Default manager hides soft-deleted records
    objects     = ActiveManager()
    objects_all = models.Manager()  # unfiltered — for admin use only

    class Meta:
        db_table = 'mpesa_accounts'
        verbose_name = 'M-Pesa Account'
        verbose_name_plural = 'M-Pesa Accounts'

    def __str__(self):
        number = self.till_number or self.paybill_number
        return f'{self.get_account_type_display()} {number} — {self.user.email}'

    def get_display_number(self):
        """Returns the number shown in payment instructions."""
        return self.till_number if self.account_type == 'till' else self.paybill_number

    def soft_delete(self):
        """Soft-deletes this account. Use instead of .delete()."""
        self.deleted_at = timezone.now()
        self.is_primary = False
        self.save(update_fields=['deleted_at', 'is_primary'])

    @transaction.atomic
    def save(self, *args, **kwargs):
        """
        Ensures only one is_primary account exists per user.
        Uses transaction.atomic so the update and save are one DB operation.
        If save() fails, the update() is also rolled back.
        """
        if self.is_primary:
            # Unset primary on all OTHER accounts for this user
            MpesaAccount.objects.filter(
                user=self.user,
                is_primary=True,
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class BankAccount(models.Model):
    """
    Bank account details for landlords (receive rent) and PMs (receive commission).
    Supports all major Kenyan banks.
    """
    BANK_CHOICES = [
        ('equity',     'Equity Bank'),
        ('kcb',        'KCB Bank'),
        ('cooperative','Co-operative Bank'),
        ('absa',       'Absa Bank Kenya'),
        ('stanchart',  'Standard Chartered'),
        ('ncba',       'NCBA Bank'),
        ('family',     'Family Bank'),
        ('im_bank',    'I&M Bank'),
        ('dtb',        'Diamond Trust Bank'),
        ('sidian',     'Sidian Bank'),
        ('other',      'Other'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bank_accounts',
        db_index=True,
    )
    bank_name      = models.CharField(max_length=50, choices=BANK_CHOICES)
    account_name   = models.CharField(
        max_length=200,
        help_text='Name as registered with the bank — used for payment verification.',
    )
    account_number = models.CharField(max_length=30)
    branch         = models.CharField(max_length=100, blank=True)
    is_primary     = models.BooleanField(default=False)

    # Soft delete
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects     = ActiveManager()
    objects_all = models.Manager()

    class Meta:
        db_table = 'bank_accounts'
        verbose_name = 'Bank Account'
        verbose_name_plural = 'Bank Accounts'

    def __str__(self):
        return f'{self.get_bank_name_display()} — {self.account_number} ({self.user.email})'

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.is_primary = False
        self.save(update_fields=['deleted_at', 'is_primary'])

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.is_primary:
            BankAccount.objects.filter(
                user=self.user,
                is_primary=True,
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)
