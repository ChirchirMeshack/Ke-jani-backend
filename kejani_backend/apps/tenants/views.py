import hashlib
import time

from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import UserRateThrottle

from django.conf import settings

from core.permissions import IsLandlord, IsAdmin, IsLandlordOrPropertyManager
from .models import Tenant
from .serializers import TenantProfileSerializer, TenantCreateSerializer, TenantUpdateSerializer
from .services import (
    create_tenant, update_tenant, end_tenancy,
    get_tenant_or_404, resend_invitation,
)
from apps.properties.services import get_unit_or_404, get_landlord_from_user


class UploadSignatureThrottle(UserRateThrottle):
    scope = "upload_signature"


class TenantPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class TenantListCreateView(APIView):
    """
    GET  /api/tenants/  — list all tenants across landlord's properties
    POST /api/tenants/  — create a new tenant (user + profile + lease in one call)
    """
    permission_classes = [IsAuthenticated, IsLandlordOrPropertyManager]

    def get(self, request):
        landlord = get_landlord_from_user(request.user)
        tenants = (
            Tenant.objects
            .filter(leases__unit__property__landlord=landlord, leases__status="active")
            .select_related("user")
            .prefetch_related("leases__unit__property")
            .distinct()
            .order_by("-created_at")
        )
        return Response(TenantProfileSerializer(tenants, many=True).data)

    def post(self, request):
        landlord   = get_landlord_from_user(request.user)
        serializer = TenantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        unit = get_unit_or_404(
            serializer.validated_data["unit_id"],
            landlord=landlord,
        )
        user_data, tenant_data, lease_data = serializer.split()

        tenant = create_tenant(
            landlord=landlord,
            unit=unit,
            user_data=user_data,
            tenant_data=tenant_data,
            lease_data=lease_data,
        )
        return Response(
            TenantProfileSerializer(tenant).data,
            status=status.HTTP_201_CREATED,
        )


class TenantDetailView(APIView):
    """
    GET    /api/tenants/<id>/
    PATCH  /api/tenants/<id>/
    DELETE /api/tenants/<id>/  — ends tenancy (terminates lease + vacates unit)
    """
    permission_classes = [IsAuthenticated, IsLandlordOrPropertyManager]

    def get(self, request, pk):
        landlord = get_landlord_from_user(request.user)
        tenant   = get_tenant_or_404(pk, landlord=landlord)
        return Response(TenantProfileSerializer(tenant).data)

    def patch(self, request, pk):
        landlord   = get_landlord_from_user(request.user)
        tenant     = get_tenant_or_404(pk, landlord=landlord)
        serializer = TenantUpdateSerializer(
            tenant, data=request.data, partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        tenant = update_tenant(tenant, serializer.validated_data)
        return Response(TenantProfileSerializer(tenant).data)

    def delete(self, request, pk):
        landlord = get_landlord_from_user(request.user)
        tenant   = get_tenant_or_404(pk, landlord=landlord)
        end_tenancy(tenant)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TenantByUnitView(APIView):
    """GET /api/tenants/by-unit/<unit_id>/ — get current tenant for a unit."""
    permission_classes = [IsAuthenticated, IsLandlordOrPropertyManager]

    def get(self, request, unit_id):
        landlord = get_landlord_from_user(request.user)
        unit = get_unit_or_404(unit_id, landlord=landlord)
        tenant = (
            Tenant.objects
            .filter(leases__unit=unit, leases__status="active")
            .select_related("user")
            .prefetch_related("leases__unit__property")
            .first()
        )
        if not tenant:
            return Response({"detail": "No active tenant for this unit."}, status=404)
        return Response(TenantProfileSerializer(tenant).data)


class ResendInvitationView(APIView):
    """POST /api/tenants/<id>/resend-invitation/ — resend with new temp password."""
    permission_classes = [IsAuthenticated, IsLandlordOrPropertyManager]

    def post(self, request, pk):
        landlord = get_landlord_from_user(request.user)
        tenant   = get_tenant_or_404(pk, landlord=landlord)
        resend_invitation(tenant)
        return Response({"message": "Invitation resent successfully."})


class TenantUploadSignatureView(APIView):
    """
    GET /api/tenants/upload-signature/?type=tenant_id_front|tenant_id_back
    Generates Cloudinary signing credentials for tenant ID uploads.
    Rate-limited to 10/minute.
    """
    permission_classes = [IsAuthenticated, IsLandlordOrPropertyManager]
    throttle_classes   = [UploadSignatureThrottle]
    VALID_TYPES        = ("tenant_id_front", "tenant_id_back")

    def get(self, request):
        upload_type = request.query_params.get("type")
        if upload_type not in self.VALID_TYPES:
            return Response(
                {"error": f"type must be one of: {self.VALID_TYPES}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        timestamp = int(time.time())
        folder = f"ke-jani/tenants/{request.user.uuid}/{upload_type}"
        params = f"folder={folder}&timestamp={timestamp}"
        sig = hashlib.sha1(
            f"{params}{settings.CLOUDINARY_SECRET}".encode()
        ).hexdigest()
        return Response({
            "signature":  sig,
            "timestamp":  timestamp,
            "api_key":    settings.CLOUDINARY_API_KEY,
            "folder":     folder,
            "cloud_name": settings.CLOUDINARY_CLOUD_NAME,
        })


class TenantDashboardView(APIView):
    """
    GET /api/tenants/dashboard/
    Summary stats for the landlord tenant panel:
    total tenants, expiring leases, recently added.
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request):
        landlord = get_landlord_from_user(request.user)
        from apps.leases.services import get_expiring_leases

        total = Tenant.objects.filter(
            leases__unit__property__landlord=landlord,
            leases__status="active"
        ).distinct().count()

        expiring_30 = get_expiring_leases(landlord, days=30).count()
        expiring_60 = get_expiring_leases(landlord, days=60).count()

        return Response({
            "total_active_tenants": total,
            "leases_expiring_30_days": expiring_30,
            "leases_expiring_60_days": expiring_60,
        })


# ── Admin Views ───────────────────────────────────────────────────────

class AdminTenantListView(generics.ListAPIView):
    """GET /api/tenants/admin/list/ — paginated list of all tenants."""
    serializer_class   = TenantProfileSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class   = TenantPagination

    def get_queryset(self):
        return (
            Tenant.objects_all
            .select_related("user")
            .prefetch_related("leases__unit__property")
            .order_by("-created_at")
        )
