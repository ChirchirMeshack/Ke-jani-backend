from django.urls import path
from . import views

app_name = 'properties'

urlpatterns = [
    # ── Portfolio dashboard ──────────────────────────────────────
    path('dashboard/',
         views.PropertyDashboardView.as_view(),
         name='dashboard'),

    # ── Cloudinary upload signature ──────────────────────────────
    path('upload-signature/',
         views.PropertyUploadSignatureView.as_view(),
         name='upload_signature'),

    # ── Property CRUD ────────────────────────────────────────────
    path('',
         views.PropertyListCreateView.as_view(),
         name='property_list'),

    path('<int:pk>/',
         views.PropertyDetailView.as_view(),
         name='property_detail'),

    # ── Property sub-resources ───────────────────────────────────
    path('<int:pk>/amenities/',
         views.PropertyAmenitiesView.as_view(),
         name='property_amenities'),

    path('<int:pk>/photos/',
         views.PropertyPhotosView.as_view(),
         name='property_photos'),

    path('<int:pk>/photos/reorder/',
         views.PhotoReorderView.as_view(),
         name='photo_reorder'),

    path('<int:pk>/photos/<int:photo_id>/',
         views.PropertyPhotoDeleteView.as_view(),
         name='photo_delete'),

    path('<int:pk>/penalty-rule/',
         views.PropertyPenaltyRuleView.as_view(),
         name='property_penalty_rule'),

    path('<int:pk>/units/',
         views.UnitListCreateView.as_view(),
         name='unit_list'),

    # ── Unit CRUD ────────────────────────────────────────────────
    path('units/<int:pk>/',
         views.UnitDetailView.as_view(),
         name='unit_detail'),

    path('units/<int:pk>/penalty-rule/',
         views.UnitPenaltyRuleView.as_view(),
         name='unit_penalty_rule'),

    # ── Admin ────────────────────────────────────────────────────
    path('admin/list/',
         views.AdminPropertyListView.as_view(),
         name='admin_list'),

    path('admin/<int:pk>/',
         views.AdminPropertyDetailView.as_view(),
         name='admin_detail'),
]
