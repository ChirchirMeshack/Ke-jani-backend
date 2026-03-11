from django.urls import path
from . import views

app_name = 'property_managers'

urlpatterns = [

    # ── PM profile & onboarding ───────────────────────────────────
    path('profile/',
         views.PmProfileView.as_view(),
         name='profile'),
    path('profile/update/',
         views.PmProfileUpdateView.as_view(),
         name='profile_update'),
    path('onboarding/progress/',
         views.PmOnboardingProgressView.as_view(),
         name='onboarding_progress'),
    path('onboarding/step/<str:step_name>/',
         views.PmOnboardingStepView.as_view(),
         name='onboarding_step'),
    path('upload-signature/',
         views.PmUploadSignatureView.as_view(),
         name='upload_signature'),

    # ── Service areas ─────────────────────────────────────────────
    path('service-areas/',
         views.PmServiceAreaView.as_view(),
         name='service_areas'),
    path('service-areas/<int:pk>/',
         views.PmServiceAreaDeleteView.as_view(),
         name='service_area_delete'),

    # ── PM responds to assignment requests ────────────────────────
    path('assignments/',
         views.PmAssignmentListView.as_view(),
         name='assignment_list'),
    path('assignments/<int:pk>/accept/',
         views.PmAcceptAssignmentView.as_view(),
         name='assignment_accept'),
    path('assignments/<int:pk>/decline/',
         views.PmDeclineAssignmentView.as_view(),
         name='assignment_decline'),

    # ── PM managed portfolio ──────────────────────────────────────
    path('managed-properties/',
         views.PmManagedPropertiesView.as_view(),
         name='managed_properties'),
    path('resign/<int:property_id>/',
         views.PmResignView.as_view(),
         name='resign'),
    path('commissions/',
         views.PmCommissionListView.as_view(),
         name='commissions'),
    path('dashboard/',
         views.PmDashboardView.as_view(),
         name='dashboard'),

    # ── Landlord initiates assignment ─────────────────────────────
    path('assign/',
         views.AssignExistingPmView.as_view(),
         name='assign'),
    path('invite/',
         views.InviteNewPmView.as_view(),
         name='invite'),
    path('invite/accept/',
         views.AcceptPmInviteView.as_view(),
         name='invite_accept'),
    path('remove/<int:property_id>/',
         views.RemovePmView.as_view(),
         name='remove'),
    path('search/',
         views.PmSearchView.as_view(),
         name='search'),
    path('commissions/<int:property_id>/',
         views.LandlordCommissionView.as_view(),
         name='landlord_commissions'),

    # ── Admin ─────────────────────────────────────────────────────
    path('admin/list/',
         views.AdminPmListView.as_view(),
         name='admin_list'),
    path('admin/<int:pk>/approve/',
         views.AdminApprovePmView.as_view(),
         name='admin_approve'),
    path('admin/<int:pk>/reject/',
         views.AdminRejectPmView.as_view(),
         name='admin_reject'),
]
