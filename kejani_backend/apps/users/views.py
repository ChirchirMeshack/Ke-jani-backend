"""
Views for the users app — all 22 auth API endpoints.
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.generics import GenericAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.permissions import IsAdmin, IsLandlord, IsPropertyManager

from .emails import (
    send_approval_email,
    send_rejection_email,
    send_welcome_email,
)
from .models import (
    AccessAuditLog,
    EmailVerificationToken,
    PMInvitation,
    TenantInvitation,
    User,
)
from .serializers import (
    AdminPendingUsersSerializer,
    ChangePasswordSerializer,
    CreateTenantSerializer,
    CustomTokenObtainPairSerializer,
    InvitedPMRegistrationSerializer,
    InvitedTenantRegistrationSerializer,
    LandlordRegistrationSerializer,
    PMInvitationCreateSerializer,
    PMRegistrationSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    TenantInvitationCreateSerializer,
    UserProfileSerializer,
    _get_client_ip,
    _log_audit,
)


# ──────────────────────────────────────────────────────────────────
# CUSTOM THROTTLES
# ──────────────────────────────────────────────────────────────────

class LoginRateThrottle(AnonRateThrottle):
    rate = '10/minute'


class PasswordResetRateThrottle(AnonRateThrottle):
    rate = '5/hour'


class RegistrationRateThrottle(AnonRateThrottle):
    rate = '5/hour'


# ══════════════════════════════════════════════════════════════════
# REGISTRATION
# ══════════════════════════════════════════════════════════════════

class LandlordRegistrationView(GenericAPIView):
    """POST /api/auth/register/landlord/ — Landlord self-registration."""

    serializer_class = LandlordRegistrationSerializer
    permission_classes = [AllowAny]
    throttle_classes = [RegistrationRateThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'message': 'Registration successful. Check your email to verify your account.'},
            status=status.HTTP_201_CREATED,
        )


class PMRegistrationView(GenericAPIView):
    """POST /api/auth/register/pm/ — PM self-registration."""

    serializer_class = PMRegistrationSerializer
    permission_classes = [AllowAny]
    throttle_classes = [RegistrationRateThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'message': 'Registration successful. Check your email to verify your account.'},
            status=status.HTTP_201_CREATED,
        )


class InvitedPMRegistrationView(GenericAPIView):
    """POST /api/auth/register/pm/invite/ — PM registers via landlord invite."""

    serializer_class = InvitedPMRegistrationSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'message': 'Registration successful. Check your email to verify your account.'},
            status=status.HTTP_201_CREATED,
        )


class ValidatePMInviteView(APIView):
    """GET /api/auth/register/pm/validate-invite/?token=<uuid>"""

    permission_classes = [AllowAny]

    def get(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response(
                {'error': 'Token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            invitation = PMInvitation.objects.select_related('invited_by').get(
                invite_token=token
            )
        except PMInvitation.DoesNotExist:
            return Response(
                {'valid': False, 'error': 'Invalid invitation token.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not invitation.is_valid():
            return Response(
                {'valid': False, 'error': 'This invitation has expired.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            'valid': True,
            'invited_name': invitation.invited_name,
            'invited_email': invitation.invited_email,
            'invited_by': invitation.invited_by.get_full_name(),
            'commission_rate': str(invitation.commission_rate),
        })


class InvitedTenantRegistrationView(GenericAPIView):
    """POST /api/auth/register/tenant/invite/ — Tenant registers via invite."""

    serializer_class = InvitedTenantRegistrationSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        send_welcome_email(user)
        return Response(
            {'message': 'Registration successful. You can now log in.'},
            status=status.HTTP_201_CREATED,
        )


class ValidateTenantInviteView(APIView):
    """GET /api/auth/register/tenant/validate-invite/?token=<uuid>"""

    permission_classes = [AllowAny]

    def get(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response(
                {'error': 'Token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            invitation = TenantInvitation.objects.select_related(
                'invited_by'
            ).get(invite_token=token)
        except TenantInvitation.DoesNotExist:
            return Response(
                {'valid': False, 'error': 'Invalid invitation token.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not invitation.is_valid():
            return Response(
                {'valid': False, 'error': 'This invitation has expired.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            'valid': True,
            'property_name': invitation.property_name,
            'unit_number': invitation.unit_number,
            'managed_by': invitation.invited_by.get_full_name(),
            'manager_role': invitation.invited_by.role,
            'invited_email': invitation.invited_email,
            'invited_name': invitation.invited_name,
        })


# ══════════════════════════════════════════════════════════════════
# EMAIL VERIFICATION
# ══════════════════════════════════════════════════════════════════

class VerifyEmailView(APIView):
    """GET /api/auth/verify-email/?token=<uuid>"""

    permission_classes = [AllowAny]

    def get(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response(
                {'error': 'Token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token_obj = EmailVerificationToken.objects.select_related(
                'user'
            ).get(token=token)
        except EmailVerificationToken.DoesNotExist:
            return Response(
                {'error': 'Invalid verification token.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if token_obj.is_used:
            return Response(
                {'error': 'This token has already been used.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = token_obj.user
        user.email_verified = True
        user.save(update_fields=['email_verified', 'updated_at'])
        token_obj.is_used = True
        token_obj.save(update_fields=['is_used'])

        _log_audit('email_verified', user=user, request=request)

        return Response({'message': 'Email verified successfully. Your account is pending admin approval.'})


# ══════════════════════════════════════════════════════════════════
# LOGIN / LOGOUT / TOKEN
# ══════════════════════════════════════════════════════════════════

class LoginView(TokenObtainPairView):
    """POST /api/auth/login/ — Email login with JWT."""

    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]


class LogoutView(APIView):
    """POST /api/auth/logout/ — Blacklists the refresh token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh_token') or request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'error': 'Refresh token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response(
                {'error': 'Invalid or already blacklisted token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _log_audit('logout', user=request.user, request=request)
        return Response({'message': 'Logged out successfully.'})


class CustomTokenRefreshView(TokenRefreshView):
    """POST /api/auth/token/refresh/ — Rotates refresh token."""
    pass


# ══════════════════════════════════════════════════════════════════
# DEMO LOGIN
# ══════════════════════════════════════════════════════════════════

class DemoLoginView(APIView):
    """POST /api/auth/demo/login/ — Instant demo landlord login."""

    permission_classes = [AllowAny]

    def post(self, request):
        try:
            demo_user = User.objects.get(email='demo@ke-jani.com', is_demo=True)
        except User.DoesNotExist:
            return Response(
                {'error': 'Demo mode is currently unavailable. Please try again later.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Short-lived tokens for demo
        refresh = RefreshToken.for_user(demo_user)
        refresh.set_exp(lifetime=timedelta(hours=2))
        access = refresh.access_token
        access.set_exp(lifetime=timedelta(hours=2))

        # Capture IP
        ip = _get_client_ip(request)
        if ip:
            demo_user.last_login_ip = ip
            demo_user.save(update_fields=['last_login_ip'])

        _log_audit('demo_login', user=demo_user, request=request)

        return Response({
            'access': str(access),
            'refresh': str(refresh),
            'user': {
                'uuid': str(demo_user.uuid),
                'email': demo_user.email,
                'full_name': demo_user.get_full_name(),
                'role': demo_user.role,
                'email_verified': demo_user.email_verified,
                'approval_status': demo_user.approval_status,
                'is_first_login': demo_user.is_first_login,
                'is_demo': True,
            },
            'demo_notice': 'You are in demo mode. Some features are restricted.',
        })


# ══════════════════════════════════════════════════════════════════
# USER PROFILE (me)
# ══════════════════════════════════════════════════════════════════

class UserProfileView(RetrieveUpdateAPIView):
    """GET / PATCH /api/auth/me/ — View/update own profile."""

    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


# ══════════════════════════════════════════════════════════════════
# PASSWORD
# ══════════════════════════════════════════════════════════════════

class ChangePasswordView(GenericAPIView):
    """POST /api/auth/change-password/"""

    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'message': 'Password changed successfully. Please log in again.'}
        )


class PasswordResetRequestView(GenericAPIView):
    """POST /api/auth/password/reset/ — Always returns 200."""

    serializer_class = PasswordResetRequestSerializer
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # Always 200 — email enumeration protection
        return Response(
            {'message': 'If an account with that email exists, a reset link has been sent.'}
        )


class PasswordResetConfirmView(GenericAPIView):
    """POST /api/auth/password/reset/confirm/"""

    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'message': 'Password reset successful. You can now log in.'}
        )


# ══════════════════════════════════════════════════════════════════
# LANDLORD ENDPOINTS
# ══════════════════════════════════════════════════════════════════

class LandlordCreateTenantView(GenericAPIView):
    """POST /api/auth/landlord/create-tenant/"""

    serializer_class = CreateTenantSerializer
    permission_classes = [IsLandlord]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                'message': 'Tenant account created. Temporary credentials sent via email.',
                'tenant_uuid': str(user.uuid),
            },
            status=status.HTTP_201_CREATED,
        )


class LandlordInvitePMView(GenericAPIView):
    """POST /api/auth/landlord/invite-pm/"""

    serializer_class = PMInvitationCreateSerializer
    permission_classes = [IsLandlord]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'message': 'Invitation sent successfully.'},
            status=status.HTTP_201_CREATED,
        )


class LandlordInviteTenantView(GenericAPIView):
    """POST /api/auth/landlord/invite-tenant/"""

    serializer_class = TenantInvitationCreateSerializer
    permission_classes = [IsLandlord]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'message': 'Tenant invitation sent successfully.'},
            status=status.HTTP_201_CREATED,
        )


# ══════════════════════════════════════════════════════════════════
# PROPERTY MANAGER ENDPOINTS
# ══════════════════════════════════════════════════════════════════

class PMCreateTenantView(GenericAPIView):
    """POST /api/auth/pm/create-tenant/"""

    serializer_class = CreateTenantSerializer
    permission_classes = [IsPropertyManager]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                'message': 'Tenant account created. Temporary credentials sent via email.',
                'tenant_uuid': str(user.uuid),
            },
            status=status.HTTP_201_CREATED,
        )


class PMInviteTenantView(GenericAPIView):
    """POST /api/auth/pm/invite-tenant/"""

    serializer_class = TenantInvitationCreateSerializer
    permission_classes = [IsPropertyManager]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'message': 'Tenant invitation sent successfully.'},
            status=status.HTTP_201_CREATED,
        )


# ══════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS
# ══════════════════════════════════════════════════════════════════

class AdminCreateTenantView(GenericAPIView):
    """POST /api/auth/admin/create-tenant/"""

    serializer_class = CreateTenantSerializer
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                'message': 'Tenant account created. Temporary credentials sent via email.',
                'tenant_uuid': str(user.uuid),
            },
            status=status.HTTP_201_CREATED,
        )


class AdminPendingUsersView(APIView):
    """GET /api/auth/admin/pending/ — List users awaiting approval."""

    permission_classes = [IsAdmin]

    def get(self, request):
        users = User.objects.filter(
            role__in=['landlord', 'property_manager'],
            email_verified=True,
            approval_status='pending',
            is_active=True,
        )
        serializer = AdminPendingUsersSerializer(users, many=True)
        return Response(serializer.data)


class AdminApproveUserView(APIView):
    """POST /api/auth/admin/approve/<user_uuid>/"""

    permission_classes = [IsAdmin]

    def post(self, request, user_uuid):
        try:
            user = User.objects.get(uuid=user_uuid)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if user.approval_status != 'pending':
            return Response(
                {'error': f'User is already {user.approval_status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.approval_status = 'approved'
        user.save(update_fields=['approval_status', 'updated_at'])
        send_approval_email(user)
        _log_audit(
            'account_approved',
            user=user,
            request=request,
            approved_by=request.user.email,
        )
        return Response({'message': f'{user.email} has been approved.'})


class AdminRejectUserView(APIView):
    """POST /api/auth/admin/reject/<user_uuid>/"""

    permission_classes = [IsAdmin]

    def post(self, request, user_uuid):
        try:
            user = User.objects.get(uuid=user_uuid)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if user.approval_status not in ('pending', 'approved'):
            return Response(
                {'error': f'User is already {user.approval_status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason = request.data.get('reason', '')
        user.approval_status = 'rejected'
        user.save(update_fields=['approval_status', 'updated_at'])
        user.soft_delete()
        send_rejection_email(user, reason=reason)
        _log_audit(
            'account_rejected',
            user=user,
            request=request,
            rejected_by=request.user.email,
            reason=reason,
        )
        return Response({'message': f'{user.email} has been rejected.'})
