from django.urls import path
from . import views

app_name = 'tenants'

urlpatterns = [
    # ── Dashboard summary ─────────────────────────────────────────
    path('dashboard/',
         views.TenantDashboardView.as_view(),
         name='dashboard'),

    # ── Cloudinary signing ────────────────────────────────────────
    path('upload-signature/',
         views.TenantUploadSignatureView.as_view(),
         name='upload_signature'),

    # ── Tenant CRUD ───────────────────────────────────────────────
    path('',
         views.TenantListCreateView.as_view(),
         name='tenant_list'),

    path('<int:pk>/',
         views.TenantDetailView.as_view(),
         name='tenant_detail'),

    path('<int:pk>/resend-invitation/',
         views.ResendInvitationView.as_view(),
         name='resend_invitation'),

    # ── Lookup by unit ────────────────────────────────────────────
    path('by-unit/<int:unit_id>/',
         views.TenantByUnitView.as_view(),
         name='by_unit'),

    # ── Admin ─────────────────────────────────────────────────────
    path('admin/list/',
         views.AdminTenantListView.as_view(),
         name='admin_list'),
]
