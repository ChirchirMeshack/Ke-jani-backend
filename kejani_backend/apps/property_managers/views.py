from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import UserRateThrottle
from django.utils import timezone

from core.permissions import IsLandlord, IsAdmin, IsPropertyManager
from .models import PropertyManager, PmServiceArea, PmAssignmentRequest, CommissionRecord
from .serializers import (
    PmProfileSerializer, PmProfileUpdateSerializer, PmPublicProfileSerializer,
    PmServiceAreaSerializer, PmAssignmentRequestSerializer,
    AssignExistingPmSerializer, InviteNewPmSerializer, AcceptPmInviteSerializer,
    AssignmentRespondSerializer, CommissionRecordSerializer,
)
from .services import (
    get_pm_from_user, get_pm_or_404, update_pm_profile,
    complete_pm_onboarding_step, get_cloudinary_upload_signature,
    add_service_area, remove_service_area,
    assign_existing_pm, invite_new_pm, accept_pm_invite,
    accept_assignment, decline_assignment,
    remove_pm_from_property, pm_resign_from_property,
    PmLimitError,
)
from apps.properties.services import get_property_or_404, get_landlord_from_user


class UploadSignatureThrottle(UserRateThrottle):
    scope = "upload_signature"


class PmPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ══════════════════════════════════════════════════════════════════════
#  PM Profile & Onboarding
# ══════════════════════════════════════════════════════════════════════

class PmProfileView(APIView):
    """GET /api/property-managers/profile/"""
    permission_classes = [IsAuthenticated, IsPropertyManager]

    def get(self, request):
        pm = get_pm_from_user(request.user)
        return Response(PmProfileSerializer(pm).data)


class PmProfileUpdateView(APIView):
    """PATCH /api/property-managers/profile/update/"""
    permission_classes = [IsAuthenticated, IsPropertyManager]

    def patch(self, request):
        pm = get_pm_from_user(request.user)
        serializer = PmProfileUpdateSerializer(
            pm, data=request.data, partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        pm = update_pm_profile(pm, serializer.validated_data)
        return Response(PmProfileSerializer(pm).data)


class PmOnboardingProgressView(APIView):
    """GET /api/property-managers/onboarding/progress/"""
    permission_classes = [IsAuthenticated, IsPropertyManager]

    def get(self, request):
        pm = get_pm_from_user(request.user)
        return Response(pm.onboarding_progress)


class PmOnboardingStepView(APIView):
    """POST /api/property-managers/onboarding/step/<step_name>/"""
    permission_classes = [IsAuthenticated, IsPropertyManager]

    def post(self, request, step_name):
        pm = get_pm_from_user(request.user)
        try:
            progress = complete_pm_onboarding_step(pm, step_name)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": f"Step {step_name!r} completed.", "progress": progress})


class PmUploadSignatureView(APIView):
    """GET /api/property-managers/upload-signature/?type=pm_id_front|pm_id_back"""
    permission_classes = [IsAuthenticated, IsPropertyManager]
    throttle_classes   = [UploadSignatureThrottle]

    def get(self, request):
        upload_type = request.query_params.get("type", "")
        try:
            data = get_cloudinary_upload_signature(request.user, upload_type)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data)


# ══════════════════════════════════════════════════════════════════════
#  Service Areas
# ══════════════════════════════════════════════════════════════════════

class PmServiceAreaView(APIView):
    """
    GET  /api/property-managers/service-areas/
    POST /api/property-managers/service-areas/
    """
    permission_classes = [IsAuthenticated, IsPropertyManager]

    def get(self, request):
        pm    = get_pm_from_user(request.user)
        areas = pm.service_areas.all()
        return Response(PmServiceAreaSerializer(areas, many=True).data)

    def post(self, request):
        pm         = get_pm_from_user(request.user)
        serializer = PmServiceAreaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        area, created = add_service_area(
            pm=pm,
            county=serializer.validated_data["county"],
            area=serializer.validated_data.get("area", ""),
        )
        return Response(
            PmServiceAreaSerializer(area).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PmServiceAreaDeleteView(APIView):
    """DELETE /api/property-managers/service-areas/<id>/"""
    permission_classes = [IsAuthenticated, IsPropertyManager]

    def delete(self, request, pk):
        pm = get_pm_from_user(request.user)
        remove_service_area(pm, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ══════════════════════════════════════════════════════════════════════
#  PM Assignment (PM side — respond to requests)
# ══════════════════════════════════════════════════════════════════════

class PmAssignmentListView(APIView):
    """GET /api/property-managers/assignments/"""
    permission_classes = [IsAuthenticated, IsPropertyManager]

    def get(self, request):
        pm = get_pm_from_user(request.user)
        qs = (
            PmAssignmentRequest.objects
            .filter(pm=pm)
            .select_related("landlord__user", "property")
            .order_by("-created_at")
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(PmAssignmentRequestSerializer(qs, many=True).data)


class PmAcceptAssignmentView(APIView):
    """POST /api/property-managers/assignments/<id>/accept/"""
    permission_classes = [IsAuthenticated, IsPropertyManager]

    def post(self, request, pk):
        pm = get_pm_from_user(request.user)
        try:
            req = PmAssignmentRequest.objects.select_related("property").get(pk=pk)
        except PmAssignmentRequest.DoesNotExist:
            return Response({"error": "Assignment request not found."}, status=404)
        try:
            updated = accept_assignment(pm=pm, assignment_request=req)
        except PmLimitError as e:
            return Response(e.to_response_dict(), status=status.HTTP_403_FORBIDDEN)
        return Response(PmAssignmentRequestSerializer(updated).data)


class PmDeclineAssignmentView(APIView):
    """POST /api/property-managers/assignments/<id>/decline/"""
    permission_classes = [IsAuthenticated, IsPropertyManager]

    def post(self, request, pk):
        pm         = get_pm_from_user(request.user)
        serializer = AssignmentRespondSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            req = PmAssignmentRequest.objects.get(pk=pk)
        except PmAssignmentRequest.DoesNotExist:
            return Response({"error": "Not found."}, status=404)
        updated = decline_assignment(
            pm=pm,
            assignment_request=req,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(PmAssignmentRequestSerializer(updated).data)


class PmManagedPropertiesView(APIView):
    """GET /api/property-managers/managed-properties/"""
    permission_classes = [IsAuthenticated, IsPropertyManager]

    def get(self, request):
        pm = get_pm_from_user(request.user)
        props = (
            pm.managed_properties
            .filter(deleted_at__isnull=True)
            .select_related("landlord__user")
            .prefetch_related("units")
            .order_by("name")
        )
        from apps.properties.serializers import PropertyListSerializer
        return Response(PropertyListSerializer(props, many=True).data)


class PmResignView(APIView):
    """POST /api/property-managers/resign/<property_id>/"""
    permission_classes = [IsAuthenticated, IsPropertyManager]

    def post(self, request, property_id):
        pm   = get_pm_from_user(request.user)
        prop = get_property_or_404(property_id)
        pm_resign_from_property(pm, prop)
        return Response({"message": f"You have resigned from {prop.name}."})


class PmCommissionListView(APIView):
    """GET /api/property-managers/commissions/"""
    permission_classes = [IsAuthenticated, IsPropertyManager]

    def get(self, request):
        pm = get_pm_from_user(request.user)
        qs = (
            CommissionRecord.objects
            .filter(pm=pm)
            .select_related("property")
            .order_by("-created_at")
        )
        status_f = request.query_params.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        return Response(CommissionRecordSerializer(qs, many=True).data)


class PmDashboardView(APIView):
    """GET /api/property-managers/dashboard/"""
    permission_classes = [IsAuthenticated, IsPropertyManager]

    def get(self, request):
        pm    = get_pm_from_user(request.user)
        props = pm.managed_properties.filter(deleted_at__isnull=True)
        total_props  = props.count()
        total_units  = pm.total_units_managed
        occupied     = sum(
            p.units.filter(status="occupied", deleted_at__isnull=True).count()
            for p in props
        )
        vacant       = total_units - occupied
        pending_reqs = PmAssignmentRequest.objects.filter(pm=pm, status="pending").count()
        pending_comm = CommissionRecord.objects.filter(pm=pm, status="pending").count()
        return Response({
            "total_properties":            total_props,
            "total_units_managed":         total_units,
            "occupied_units":              occupied,
            "vacant_units":                vacant,
            "pending_assignment_requests": pending_reqs,
            "pending_commissions":         pending_comm,
            "onboarding_complete":         pm.is_onboarding_complete,
            "onboarding_progress":         pm.onboarding_progress,
        })


# ══════════════════════════════════════════════════════════════════════
#  Landlord-Side Views
# ══════════════════════════════════════════════════════════════════════

class AssignExistingPmView(APIView):
    """POST /api/property-managers/assign/"""
    permission_classes = [IsAuthenticated, IsLandlord]

    def post(self, request):
        landlord   = get_landlord_from_user(request.user)
        serializer = AssignExistingPmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        pm   = get_pm_or_404(d["pm_id"])
        prop = get_property_or_404(d["property_id"], landlord=landlord)

        req = assign_existing_pm(
            landlord=landlord,
            pm=pm,
            property_instance=prop,
            terms_data=d,
        )
        return Response(
            PmAssignmentRequestSerializer(req).data,
            status=status.HTTP_201_CREATED,
        )


class InviteNewPmView(APIView):
    """POST /api/property-managers/invite/"""
    permission_classes = [IsAuthenticated, IsLandlord]

    def post(self, request):
        landlord   = get_landlord_from_user(request.user)
        serializer = InviteNewPmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d    = serializer.validated_data
        prop = get_property_or_404(d["property_id"], landlord=landlord)

        req = invite_new_pm(
            landlord=landlord,
            invite_data={"email": d["email"], "name": d["name"], "phone": d["phone"]},
            property_instance=prop,
            terms_data=d,
        )
        return Response(
            {"message": f"Invitation sent to {d['email']}.", "request_id": req.id},
            status=status.HTTP_201_CREATED,
        )


class AcceptPmInviteView(APIView):
    """POST /api/property-managers/invite/accept/ — public endpoint (AllowAny)"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AcceptPmInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        pm, req = accept_pm_invite(
            token=d["token"],
            user_data={
                "first_name": d["first_name"],
                "last_name":  d["last_name"],
                "email":      d["email"],
                "phone":      d["phone"],
                "password":   d["password"],
            },
        )
        return Response({
            "message":  "Account created and property assigned successfully.",
            "pm_id":    pm.id,
            "property": req.property.name,
        }, status=status.HTTP_201_CREATED)


class RemovePmView(APIView):
    """DELETE /api/property-managers/remove/<property_id>/"""
    permission_classes = [IsAuthenticated, IsLandlord]

    def delete(self, request, property_id):
        landlord = get_landlord_from_user(request.user)
        prop     = get_property_or_404(property_id, landlord=landlord)
        remove_pm_from_property(landlord, prop)
        return Response({"message": "Property manager removed. Property is now self-managed."})


class PmSearchView(APIView):
    """GET /api/property-managers/search/?county=nairobi&area=Kilimani"""
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request):
        county = request.query_params.get("county", "")
        area   = request.query_params.get("area", "")

        qs = (
            PropertyManager.objects
            .filter(is_searchable=True, approval_status="approved")
            .select_related("user")
            .prefetch_related("service_areas")
        )
        if county:
            qs = qs.filter(service_areas__county=county)
        if area:
            qs = qs.filter(service_areas__area__icontains=area)

        qs = qs.distinct()
        return Response(PmPublicProfileSerializer(qs, many=True).data)


class LandlordCommissionView(APIView):
    """GET /api/property-managers/commissions/<property_id>/"""
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request, property_id):
        landlord = get_landlord_from_user(request.user)
        prop     = get_property_or_404(property_id, landlord=landlord)
        qs       = CommissionRecord.objects.filter(property=prop).select_related("pm__user")
        return Response(CommissionRecordSerializer(qs, many=True).data)


# ══════════════════════════════════════════════════════════════════════
#  Admin Views
# ══════════════════════════════════════════════════════════════════════

class AdminPmListView(generics.ListAPIView):
    """GET /api/property-managers/admin/list/"""
    serializer_class   = PmProfileSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class   = PmPagination

    def get_queryset(self):
        return (
            PropertyManager.objects_all
            .select_related("user")
            .prefetch_related("service_areas")
            .order_by("-created_at")
        )


class AdminApprovePmView(APIView):
    """POST /api/property-managers/admin/<id>/approve/"""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        pm = get_pm_or_404(pk)
        pm.approval_status     = "approved"
        pm.approved_by         = request.user
        pm.approved_at         = timezone.now()
        pm.subscription_active = True
        pm.save(update_fields=[
            "approval_status", "approved_by", "approved_at",
            "subscription_active", "updated_at",
        ])
        # Also update User's approval_status so IsPropertyManager permission works
        pm.user.approval_status = "approved"
        pm.user.save(update_fields=["approval_status"])
        return Response({"message": f"{pm.user.full_name} approved."})


class AdminRejectPmView(APIView):
    """POST /api/property-managers/admin/<id>/reject/"""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        reason = request.data.get("reason", "")
        if not reason:
            return Response({"error": "reason is required."}, status=400)
        pm = get_pm_or_404(pk)
        pm.approval_status  = "rejected"
        pm.rejection_reason = reason
        pm.save(update_fields=["approval_status", "rejection_reason", "updated_at"])
        return Response({"message": f"{pm.user.full_name} rejected."})
