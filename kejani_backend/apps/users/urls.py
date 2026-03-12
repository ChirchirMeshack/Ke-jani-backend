from django.urls import path

from . import views

app_name = 'users'

urlpatterns = [
    # ── Registration ──────────────────────────────────────────────
    path('register/landlord/', views.LandlordRegistrationView.as_view(), name='register-landlord'),
    path('register/pm/', views.PMRegistrationView.as_view(), name='register-pm'),
    path('register/pm/invite/', views.InvitedPMRegistrationView.as_view(), name='register-pm-invite'),
    path('register/pm/validate-invite/', views.ValidatePMInviteView.as_view(), name='validate-pm-invite'),
    path('register/tenant/invite/', views.InvitedTenantRegistrationView.as_view(), name='register-tenant-invite'),
    path('register/tenant/validate-invite/', views.ValidateTenantInviteView.as_view(), name='validate-tenant-invite'),

    # ── Email verification ────────────────────────────────────────
    path('verify-email/', views.VerifyEmailView.as_view(), name='verify-email'),

    # ── Login / Logout / Token ────────────────────────────────────
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('token/refresh/', views.CustomTokenRefreshView.as_view(), name='token-refresh'),
    path('demo/login/', views.DemoLoginView.as_view(), name='demo-login'),

    # ── User profile ──────────────────────────────────────────────
    path('me/', views.UserProfileView.as_view(), name='user-profile'),

    # ── Password ──────────────────────────────────────────────────
    path('change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    path('password/reset/', views.PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password/reset/confirm/', views.PasswordResetConfirmView.as_view(), name='password-reset-confirm'),

    # ── Landlord endpoints ────────────────────────────────────────
    path('landlord/create-tenant/', views.LandlordCreateTenantView.as_view(), name='landlord-create-tenant'),
    path('landlord/invite-pm/', views.LandlordInvitePMView.as_view(), name='landlord-invite-pm'),
    path('landlord/invite-tenant/', views.LandlordInviteTenantView.as_view(), name='landlord-invite-tenant'),

    # ── PM endpoints ──────────────────────────────────────────────
    path('pm/create-tenant/', views.PMCreateTenantView.as_view(), name='pm-create-tenant'),
    path('pm/invite-tenant/', views.PMInviteTenantView.as_view(), name='pm-invite-tenant'),

    # ── Admin endpoints ───────────────────────────────────────────
    path('admin/create-tenant/', views.AdminCreateTenantView.as_view(), name='admin-create-tenant'),
    path('admin/pending/', views.AdminPendingUsersView.as_view(), name='admin-pending'),
    path('admin/approve/<uuid:user_uuid>/', views.AdminApproveUserView.as_view(), name='admin-approve'),
    path('admin/reject/<uuid:user_uuid>/', views.AdminRejectUserView.as_view(), name='admin-reject'),
]
