from django.db import transaction
from .models import MpesaAccount, BankAccount


def validate_mpesa_number(account_type, till_number='', paybill_number=''):
    """
    Validates M-Pesa till or paybill number format.
    Kenyan till/paybill numbers are 5-7 digits (doc says '6-digit'
    but in practice some are 5. We accept 5-7 to be safe).

    Returns: dict of field errors (empty dict = valid).
    """
    errors = {}
    if account_type == 'till':
        if not till_number:
            errors['till_number'] = 'Till number is required.'
        elif not till_number.isdigit() or not (5 <= len(till_number) <= 7):
            errors['till_number'] = 'Enter a valid 5–7 digit till number.'
    elif account_type == 'paybill':
        if not paybill_number:
            errors['paybill_number'] = 'Paybill number is required.'
        elif not paybill_number.isdigit() or not (5 <= len(paybill_number) <= 7):
            errors['paybill_number'] = 'Enter a valid 5–7 digit paybill number.'
    return errors


@transaction.atomic
def add_mpesa_account(user, validated_data):
    """
    Creates a new M-Pesa account for a user.
    Automatically sets is_primary=True if this is the user's first account.

    NOTE: is_primary from the client is intentionally IGNORED here.
    The client should never control which account is primary directly —
    use set_primary_mpesa_account() for that.

    Returns: the created MpesaAccount instance.
    """
    # Strip client-provided is_primary — service controls this
    validated_data.pop('is_primary', None)

    is_first = not MpesaAccount.objects.filter(user=user).exists()
    if is_first:
        validated_data['is_primary'] = True

    return MpesaAccount.objects.create(user=user, **validated_data)


@transaction.atomic
def set_primary_mpesa_account(user, account_id):
    """
    Sets a specific M-Pesa account as the primary receiving account.
    All other accounts for this user are set to is_primary=False.

    :raises MpesaAccount.DoesNotExist: if account_id not found for this user.
    Returns: the updated MpesaAccount instance.
    """
    account = MpesaAccount.objects.get(id=account_id, user=user)
    account.is_primary = True
    account.save()  # save() handles unsetting other accounts atomically
    return account


@transaction.atomic
def add_bank_account(user, validated_data):
    """
    Creates a new bank account for a user.
    Automatically sets is_primary=True if this is the user's first bank account.

    NOTE: is_primary from the client is intentionally IGNORED.
    Returns: the created BankAccount instance.
    """
    validated_data.pop('is_primary', None)

    is_first = not BankAccount.objects.filter(user=user).exists()
    if is_first:
        validated_data['is_primary'] = True

    return BankAccount.objects.create(user=user, **validated_data)


def get_primary_mpesa_account(user):
    """Returns the primary M-Pesa account or None."""
    return MpesaAccount.objects.filter(user=user, is_primary=True).first()


def get_primary_bank_account(user):
    """Returns the primary bank account or None."""
    return BankAccount.objects.filter(user=user, is_primary=True).first()
