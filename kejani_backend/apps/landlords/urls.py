from django.urls import path
from . import views

app_name = 'landlords'

urlpatterns = [
    # ── Landlord-facing ─────────────────────────────────────────
    path('profile/',
         views.LandlordProfileView.as_view(),
         name='profile'),

    path('profile/update/',
         views.LandlordBasicUpdateView.as_view(),
         name='profile_update'),

    path('onboarding/progress/',
         views.LandlordOnboardingProgressView.as_view(),
         name='onboarding_progress'),

    path('onboarding/step/profile/',
         views.LandlordProfileStepView.as_view(),
         name='onboarding_step_profile'),

    path('upload-signature/',
         views.CloudinaryUploadSignatureView.as_view(),
         name='upload_signature'),

    # ── Admin-facing ─────────────────────────────────────────────
    path('admin/list/',
         views.AdminLandlordListView.as_view(),
         name='admin_list'),

    path('admin/<int:pk>/',
         views.AdminLandlordDetailView.as_view(),
         name='admin_detail'),
]
