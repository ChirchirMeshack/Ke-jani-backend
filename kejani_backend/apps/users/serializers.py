"""
Serializers for the users app — covers registration, login,
password management, invitations, user profile, and admin endpoints.
"""
import re
import secrets
import string
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .emails import (
    send_admin_new_registration_alert,
    send_temp_credentials_email,
    send_verification_email,
)
from .models import (
    AccessAuditLog,
    EmailVerificationToken,
    PMInvitation,
    PasswordResetToken,
    TenantInvitation,
    User,
)


# ──────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────

def _normalize_phone(phone: str) -> str:
    """Normalize Kenyan phone to E.164 (+254…). Pass-through if already ok."""
    if not phone:
        return phone
    phone = phone.strip().replace(' ', '').replace('-', '')
    if phone.startswith('0') and len(phone) == 10:
        phone = '+254' + phone[1:]
    if phone.startswith('254') and not phone.startswith('+'):
        phone = '+' + phone
    return phone


def _generate_temp_password(length=12):
    """Generate a secure temporary password."""
    chars = string.ascii_letters + string.digits + '!@#$%'
    return ''.join(secrets.choice(chars) for _ in range(length))


def _get_client_ip(request):
    """Extract client IP from request."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log_audit(event, user=None, request=None, **details):
    """Create an AccessAuditLog entry."""
    ip = _get_client_ip(request) if request else None
    AccessAuditLog.objects.create(
        event=event,
        user=user,
        ip_address=ip,
        role=getattr(user, 'role', ''),
        details=details,
    )


# ──────────────────────────────────────────────────────────────────
# USER PROFILE
# ──────────────────────────────────────────────────────────────────

class UserProfileSerializer(serializers.ModelSerializer):
    """Read / update for the /me/ endpoint."""

    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = User
        fields = [
            'uuid', 'email', 'first_name', 'last_name', 'full_name',
            'phone', 'role', 'email_verified', 'approval_status',
            'is_first_login', 'is_demo', 'created_at',
        ]
        read_only_fields = [
            'uuid', 'email', 'role', 'email_verified', 'approval_status',
            'is_first_login', 'is_demo', 'created_at',
        ]


# ──────────────────────────────────────────────────────────────────
# REGISTRATION — LANDLORD
# ──────────────────────────────────────────────────────────────────

ESTIMATED_PROPERTIES_CHOICES = ['1-10', '11-30', '31-75', '76-150', '150+']
LANDLORD_TIERS = ['solo', 'starter', 'growth', 'professional', 'enterprise']


class LandlordRegistrationSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    id_number = serializers.CharField(max_length=8)
    estimated_properties = serializers.ChoiceField(choices=ESTIMATED_PROPERTIES_CHOICES)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15)
    subscription_tier = serializers.ChoiceField(choices=LANDLORD_TIERS)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    terms_agreed = serializers.BooleanField()

    def validate_id_number(self, value):
        if not re.fullmatch(r'\d{7,8}', value):
            raise serializers.ValidationError(
                'National ID must be 7-8 digits.'
            )
        return value

    def validate_email(self, value):
        value = value.lower()
        if User.objects_all.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate_terms_agreed(self, value):
        if not value:
            raise serializers.ValidationError('You must agree to the terms.')
        return value

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError(
                {'password_confirm': 'Passwords do not match.'}
            )
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        validated_data.pop('terms_agreed')
        id_number = validated_data.pop('id_number')
        estimated_properties = validated_data.pop('estimated_properties')
        subscription_tier = validated_data.pop('subscription_tier')
        phone = _normalize_phone(validated_data.pop('phone'))
        password = validated_data.pop('password')

        user = User.objects.create_user(
            email=validated_data['email'],
            password=password,
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone=phone,
            role='landlord',
            approval_status='pending',
            email_verified=False,
            is_active=True,
            is_first_login=False,
        )

        # Store profile data temporarily on the instance
        # (read by apps/landlords/ when that app is built)
        user._id_number = id_number
        user._estimated_properties = estimated_properties
        user._subscription_tier = subscription_tier

        # Create verification token & send emails
        token_obj = EmailVerificationToken.objects.create(user=user)
        send_verification_email(user, token_obj.token)
        send_admin_new_registration_alert(user)

        # Audit
        _log_audit(
            'registration',
            user=user,
            request=self.context.get('request'),
            role='landlord',
        )

        return user


# ──────────────────────────────────────────────────────────────────
# REGISTRATION — PROPERTY MANAGER (self-signup)
# ──────────────────────────────────────────────────────────────────

PM_TIERS = ['starter_pm', 'professional_pm', 'enterprise_pm']


class PMRegistrationSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    company_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    id_number = serializers.CharField(max_length=20)
    commission_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15)
    subscription_tier = serializers.ChoiceField(choices=PM_TIERS)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    terms_agreed = serializers.BooleanField()

    def validate_id_number(self, value):
        if not re.fullmatch(r'[A-Za-z0-9\-]{3,20}', value):
            raise serializers.ValidationError(
                'ID must be alphanumeric (3-20 characters).'
            )
        return value

    def validate_commission_rate(self, value):
        if not (10 <= value <= 20):
            raise serializers.ValidationError(
                'Commission rate must be between 10% and 20%.'
            )
        return value

    def validate_email(self, value):
        value = value.lower()
        if User.objects_all.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate_terms_agreed(self, value):
        if not value:
            raise serializers.ValidationError('You must agree to the terms.')
        return value

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError(
                {'password_confirm': 'Passwords do not match.'}
            )
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        validated_data.pop('terms_agreed')
        id_number = validated_data.pop('id_number')
        commission_rate = validated_data.pop('commission_rate')
        subscription_tier = validated_data.pop('subscription_tier')
        company_name = validated_data.pop('company_name', '')
        phone = _normalize_phone(validated_data.pop('phone'))
        password = validated_data.pop('password')

        user = User.objects.create_user(
            email=validated_data['email'],
            password=password,
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone=phone,
            role='property_manager',
            approval_status='pending',
            email_verified=False,
            is_active=True,
            is_first_login=False,
        )

        user._id_number = id_number
        user._commission_rate = commission_rate
        user._subscription_tier = subscription_tier
        user._company_name = company_name

        token_obj = EmailVerificationToken.objects.create(user=user)
        send_verification_email(user, token_obj.token)
        send_admin_new_registration_alert(user)

        _log_audit(
            'registration',
            user=user,
            request=self.context.get('request'),
            role='property_manager',
        )

        return user


# ──────────────────────────────────────────────────────────────────
# REGISTRATION — PM VIA LANDLORD INVITE
# ──────────────────────────────────────────────────────────────────

class InvitedPMRegistrationSerializer(serializers.Serializer):
    invite_token = serializers.UUIDField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    company_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    id_number = serializers.CharField(max_length=20)
    commission_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15)
    subscription_tier = serializers.ChoiceField(choices=PM_TIERS)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    terms_agreed = serializers.BooleanField()

    def validate_invite_token(self, value):
        try:
            invitation = PMInvitation.objects.get(invite_token=value)
        except PMInvitation.DoesNotExist:
            raise serializers.ValidationError('Invalid invitation token.')
        if not invitation.is_valid():
            raise serializers.ValidationError('This invitation has expired or been used.')
        self._invitation = invitation
        return value

    def validate_id_number(self, value):
        if not re.fullmatch(r'[A-Za-z0-9\-]{3,20}', value):
            raise serializers.ValidationError('ID must be alphanumeric (3-20 characters).')
        return value

    def validate_commission_rate(self, value):
        if not (10 <= value <= 20):
            raise serializers.ValidationError('Commission rate must be between 10% and 20%.')
        return value

    def validate_email(self, value):
        value = value.lower()
        if User.objects_all.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate_terms_agreed(self, value):
        if not value:
            raise serializers.ValidationError('You must agree to the terms.')
        return value

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
            
        invitation = getattr(self, '_invitation', None)
        if invitation and data.get('email', '').strip().lower() != invitation.invited_email.lower():
            raise serializers.ValidationError({
                'email': 'This email does not match the invitation.'
            })
            
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        validated_data.pop('terms_agreed')
        validated_data.pop('invite_token')
        id_number = validated_data.pop('id_number')
        commission_rate = validated_data.pop('commission_rate')
        subscription_tier = validated_data.pop('subscription_tier')
        company_name = validated_data.pop('company_name', '')
        phone = _normalize_phone(validated_data.pop('phone'))
        password = validated_data.pop('password')

        user = User.objects.create_user(
            email=validated_data['email'],
            password=password,
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone=phone,
            role='property_manager',
            approval_status='pending',
            email_verified=False,
            is_active=True,
            is_first_login=False,
        )

        user._id_number = id_number
        user._commission_rate = commission_rate
        user._subscription_tier = subscription_tier
        user._company_name = company_name

        # Mark invitation as accepted
        invitation = self._invitation
        invitation.accepted_by = user
        invitation.status = 'accepted'
        invitation.save(update_fields=['accepted_by', 'status'])

        # Verification email & admin notification
        token_obj = EmailVerificationToken.objects.create(user=user)
        send_verification_email(user, token_obj.token)
        send_admin_new_registration_alert(user)

        _log_audit(
            'registration',
            user=user,
            request=self.context.get('request'),
            role='property_manager',
            invited_by=invitation.invited_by.email,
        )
        _log_audit(
            'invitation_accepted',
            user=user,
            request=self.context.get('request'),
            invitation_id=invitation.pk,
        )

        return user


# ──────────────────────────────────────────────────────────────────
# REGISTRATION — TENANT VIA INVITE LINK
# ──────────────────────────────────────────────────────────────────

class InvitedTenantRegistrationSerializer(serializers.Serializer):
    invite_token = serializers.UUIDField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    id_number = serializers.CharField(max_length=8)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15, required=False, allow_blank=True)
    password = serializers.CharField(
        write_only=True, validators=[validate_password]
    )
    password_confirm = serializers.CharField(write_only=True)

    def validate_invite_token(self, value):
        try:
            invitation = TenantInvitation.objects.get(invite_token=value)
        except TenantInvitation.DoesNotExist:
            raise serializers.ValidationError('Invalid invitation token.')
        if not invitation.is_valid():
            raise serializers.ValidationError('This invitation has expired or been used.')
        self._invitation = invitation
        return value

    def validate_id_number(self, value):
        if not re.fullmatch(r'\d{7,8}', value):
            raise serializers.ValidationError('National ID must be 7-8 digits.')
        return value

    def validate_email(self, value):
        value = value.lower()
        if User.objects_all.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
            
        invitation = getattr(self, '_invitation', None)
        if invitation and data.get('email', '').strip().lower() != invitation.invited_email.lower():
            raise serializers.ValidationError({
                'email': 'This email does not match the invitation.'
            })
            
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        validated_data.pop('invite_token')
        id_number = validated_data.pop('id_number')
        phone = _normalize_phone(validated_data.pop('phone', ''))
        password = validated_data.pop('password')

        user = User.objects.create_user(
            email=validated_data['email'],
            password=password,
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone=phone,
            role='tenant',
            approval_status='not_required',
            email_verified=True,
            is_active=True,
            is_first_login=False,   # they set their own password
        )

        user._id_number = id_number

        invitation = self._invitation
        invitation.accepted_by = user
        invitation.status = 'accepted'
        invitation.save(update_fields=['accepted_by', 'status'])

        _log_audit(
            'registration',
            user=user,
            request=self.context.get('request'),
            role='tenant',
        )
        _log_audit(
            'invitation_accepted',
            user=user,
            request=self.context.get('request'),
            invitation_id=invitation.pk,
        )

        return user


# ──────────────────────────────────────────────────────────────────
# CREATE TENANT (admin / landlord / PM)
# ──────────────────────────────────────────────────────────────────

class CreateTenantSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15, required=False, allow_blank=True)
    id_number = serializers.CharField(max_length=8)

    def validate_id_number(self, value):
        if not re.fullmatch(r'\d{7,8}', value):
            raise serializers.ValidationError('National ID must be 7-8 digits.')
        return value

    def validate_email(self, value):
        value = value.lower()
        if User.objects_all.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def create(self, validated_data):
        id_number = validated_data.pop('id_number')
        phone = _normalize_phone(validated_data.pop('phone', ''))
        temp_password = _generate_temp_password()

        user = User.objects.create_user(
            email=validated_data['email'],
            password=temp_password,
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone=phone,
            role='tenant',
            approval_status='not_required',
            email_verified=True,
            is_active=True,
            is_first_login=True,
        )

        user._id_number = id_number

        # Send temporary credentials
        send_temp_credentials_email(user, temp_password)

        creator = self.context.get('request').user
        _log_audit(
            'registration',
            user=user,
            request=self.context.get('request'),
            role='tenant',
            created_by=creator.email,
        )

        return user


# ──────────────────────────────────────────────────────────────────
# LOGIN (Custom JWT)
# ──────────────────────────────────────────────────────────────────

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    remember_me = serializers.BooleanField(default=False, required=False)

    def validate(self, attrs):
        remember_me = attrs.pop('remember_me', False)
        email = attrs.get(self.username_field, '').lower()
        attrs[self.username_field] = email

        # Authenticate
        try:
            data = super().validate(attrs)
        except Exception:
            # Log failed attempt
            request = self.context.get('request')
            _log_audit(
                'login_failed',
                request=request,
                email=email,
                reason='invalid_credentials',
            )
            raise

        user = self.user

        # ── Role-based login blocks ──────────────────────────
        if user.role in ('landlord', 'property_manager'):
            if not user.email_verified:
                raise serializers.ValidationError(
                    'Please verify your email before logging in.'
                )
            if user.approval_status == 'pending':
                raise serializers.ValidationError(
                    'Your account is pending admin approval.'
                )
            if user.approval_status == 'rejected':
                raise serializers.ValidationError(
                    'Your account registration was not approved.'
                )
            if user.approval_status == 'suspended':
                raise serializers.ValidationError(
                    'Your account has been suspended. Contact support.'
                )

        if not user.is_active:
            raise serializers.ValidationError('Account not active.')

        # ── Adjust refresh token lifetime for remember_me ────
        if not remember_me:
            # Override with 1-day refresh token
            refresh = RefreshToken.for_user(user)
            refresh.set_exp(lifetime=timedelta(days=1))
            data['refresh'] = str(refresh)
            data['access'] = str(refresh.access_token)

        # ── Capture IP ───────────────────────────────────────
        request = self.context.get('request')
        ip = _get_client_ip(request) if request else None
        if ip:
            user.last_login_ip = ip
            user.save(update_fields=['last_login_ip'])

        # ── Add user info to response ───────────────────────
        data['user'] = {
            'uuid': str(user.uuid),
            'email': user.email,
            'full_name': user.get_full_name(),
            'role': user.role,
            'email_verified': user.email_verified,
            'approval_status': user.approval_status,
            'is_first_login': user.is_first_login,
            'is_demo': user.is_demo,
        }

        # ── Audit ────────────────────────────────────────────
        _log_audit('login_success', user=user, request=request)

        return data


# ──────────────────────────────────────────────────────────────────
# CHANGE PASSWORD
# ──────────────────────────────────────────────────────────────────

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True, validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value

    def validate(self, data):
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError(
                {'new_password_confirm': 'Passwords do not match.'}
            )
        return data

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.is_first_login = False
        user.save(update_fields=['password', 'is_first_login', 'updated_at'])
        _log_audit(
            'password_changed',
            user=user,
            request=self.context.get('request'),
        )
        return user


# ──────────────────────────────────────────────────────────────────
# PASSWORD RESET — REQUEST
# ──────────────────────────────────────────────────────────────────

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def save(self, **kwargs):
        email = self.validated_data['email'].lower()
        request = self.context.get('request')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Always log the attempt even if user not found
            _log_audit(
                'password_reset_requested',
                request=request,
                email=email,
                found=False,
            )
            return  # silent — don't reveal whether email exists

        # Invalidate existing tokens
        PasswordResetToken.objects.filter(user=user, is_used=False).update(
            is_used=True
        )

        # Create new token
        from .emails import send_password_reset_email

        token_obj = PasswordResetToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        send_password_reset_email(user, token_obj.token)

        _log_audit(
            'password_reset_requested',
            user=user,
            request=request,
        )


# ──────────────────────────────────────────────────────────────────
# PASSWORD RESET — CONFIRM
# ──────────────────────────────────────────────────────────────────

class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    new_password = serializers.CharField(
        write_only=True, validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_token(self, value):
        try:
            token_obj = PasswordResetToken.objects.select_related('user').get(
                token=value
            )
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError('Invalid reset token.')
        if not token_obj.is_valid():
            raise serializers.ValidationError('This reset link has expired or already been used.')
        self._token_obj = token_obj
        return value

    def validate(self, data):
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError(
                {'new_password_confirm': 'Passwords do not match.'}
            )
        return data

    def save(self, **kwargs):
        token_obj = self._token_obj
        user = token_obj.user
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password', 'updated_at'])
        token_obj.is_used = True
        token_obj.save(update_fields=['is_used'])
        _log_audit(
            'password_reset_completed',
            user=user,
            request=self.context.get('request'),
        )
        return user


# ──────────────────────────────────────────────────────────────────
# PM INVITATION (landlord creates)
# ──────────────────────────────────────────────────────────────────

class PMInvitationCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15, required=False, allow_blank=True)
    commission_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    property_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_email(self, value):
        value = value.lower()
        if User.objects_all.filter(email=value).exists():
            raise serializers.ValidationError(
                'This PM already has an account. Ask them to log in '
                'and accept the assignment.'
            )
        return value

    def validate_commission_rate(self, value):
        if not (10 <= value <= 20):
            raise serializers.ValidationError(
                'Commission rate must be between 10% and 20%.'
            )
        return value

    def create(self, validated_data):
        from .emails import send_pm_invitation_email

        landlord = self.context['request'].user
        invitation = PMInvitation.objects.create(
            invited_by=landlord,
            invited_email=validated_data['email'],
            invited_name=validated_data['name'],
            invited_phone=_normalize_phone(validated_data.get('phone', '')),
            commission_rate=validated_data['commission_rate'],
            property_id=validated_data.get('property_id'),
            expires_at=timezone.now() + timedelta(days=7),
        )
        send_pm_invitation_email(invitation)
        _log_audit(
            'invitation_sent',
            user=landlord,
            request=self.context.get('request'),
            invited_email=invitation.invited_email,
            type='pm',
        )
        return invitation


# ──────────────────────────────────────────────────────────────────
# TENANT INVITATION (landlord/PM creates)
# ──────────────────────────────────────────────────────────────────

class TenantInvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=15, required=False, allow_blank=True)
    unit_id = serializers.IntegerField(required=False, allow_null=True)
    unit_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    property_name = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_email(self, value):
        return value.lower()

    def create(self, validated_data):
        from .emails import send_tenant_invitation_email

        inviter = self.context['request'].user
        invitation = TenantInvitation.objects.create(
            invited_by=inviter,
            invited_email=validated_data['email'],
            invited_name=validated_data.get('name', ''),
            invited_phone=_normalize_phone(validated_data.get('phone', '')),
            unit_id=validated_data.get('unit_id'),
            unit_number=validated_data.get('unit_number', ''),
            property_name=validated_data.get('property_name', ''),
            expires_at=timezone.now() + timedelta(days=7),
        )
        send_tenant_invitation_email(invitation)
        _log_audit(
            'invitation_sent',
            user=inviter,
            request=self.context.get('request'),
            invited_email=invitation.invited_email,
            type='tenant',
        )
        return invitation


# ──────────────────────────────────────────────────────────────────
# ADMIN — PENDING USERS LIST
# ──────────────────────────────────────────────────────────────────

class AdminPendingUsersSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = User
        fields = [
            'uuid', 'email', 'full_name', 'phone', 'role',
            'email_verified', 'approval_status', 'created_at',
        ]
