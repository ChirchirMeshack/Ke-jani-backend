from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from core.permissions import IsLandlordOrPropertyManager
from .models import Lease
from .serializers import LeaseSerializer, LeaseRenewSerializer
from .services import get_lease_or_404, update_lease, renew_lease, get_expiring_leases


class LandlordLeaseListView(APIView):
    """GET /api/leases/ — all active leases across landlord's properties."""
    permission_classes = [IsAuthenticated, IsLandlordOrPropertyManager]

    def get(self, request):
        from apps.properties.services import get_landlord_from_user
        landlord = get_landlord_from_user(request.user)
        qs = (
            Lease.objects
            .filter(unit__property__landlord=landlord)
            .select_related("tenant__user", "unit__property")
            .order_by("-created_at")
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(LeaseSerializer(qs, many=True).data)


class LeaseDetailView(APIView):
    """
    GET   /api/leases/<id>/ — landlord, PM, or the tenant themselves
    PATCH /api/leases/<id>/ — landlord or PM only
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        lease = get_lease_or_404(pk)
        # Tenants may only view their own lease
        if hasattr(request.user, "tenant_profile"):
            if lease.tenant.user != request.user:
                from rest_framework.exceptions import NotFound
                raise NotFound("Lease not found.")
        return Response(LeaseSerializer(lease).data)

    def patch(self, request, pk):
        lease = get_lease_or_404(pk)
        serializer = LeaseSerializer(lease, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        lease = update_lease(lease, serializer.validated_data)
        return Response(LeaseSerializer(lease).data)


class LeaseRenewView(APIView):
    """POST /api/leases/<id>/renew/ — creates a new lease as a renewal."""
    permission_classes = [IsAuthenticated, IsLandlordOrPropertyManager]

    def post(self, request, pk):
        lease      = get_lease_or_404(pk)
        serializer = LeaseRenewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_lease = renew_lease(
            old_lease=lease,
            new_end_date=serializer.validated_data["new_end_date"],
            new_monthly_rent=serializer.validated_data.get("new_monthly_rent"),
        )
        return Response(LeaseSerializer(new_lease).data)


class ExpiringLeasesView(APIView):
    """
    GET /api/leases/expiring/?days=30
    Returns leases expiring within N days. Default 30, max 90.
    """
    permission_classes = [IsAuthenticated, IsLandlordOrPropertyManager]

    def get(self, request):
        from apps.properties.services import get_landlord_from_user
        try:
            days = min(int(request.query_params.get("days", 30)), 90)
        except ValueError:
            days = 30
        landlord = get_landlord_from_user(request.user)
        leases   = get_expiring_leases(landlord, days=days)
        return Response({
            "days_window": days,
            "count":       leases.count(),
            "leases":      LeaseSerializer(leases, many=True).data,
        })
