from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import UserRateThrottle

from core.permissions import IsLandlord, IsAdmin, IsLandlordOrPropertyManager
from .models import Property, Unit, PropertyPhoto, PenaltyRule
from .serializers import (
    PropertyListSerializer, PropertyDetailSerializer,
    PropertyCreateSerializer, PropertyUpdateSerializer,
    PropertyAmenitySerializer, AmenitiesBulkSerializer,
    PropertyPhotoSerializer, PhotoReorderSerializer,
    UnitSerializer, PenaltyRuleSerializer,
)
from .services import (
    get_property_or_404, get_unit_or_404, get_landlord_from_user,
    create_property, update_property,
    create_unit, update_unit,
    set_amenities, add_photo, reorder_photos,
    get_or_create_property_penalty_rule, update_penalty_rule, set_unit_penalty_rule,
    get_cloudinary_upload_signature,
)
from .exceptions import SubscriptionLimitError


class UploadSignatureThrottle(UserRateThrottle):
    scope = "upload_signature"

class PropertyPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _get_landlord(request):
    """Helper: returns landlord profile from request.user."""
    return get_landlord_from_user(request.user)


def _handle_limit_error(exc):
    """Converts a SubscriptionLimitError into a 403 Response."""
    return Response(exc.to_response_dict(), status=status.HTTP_403_FORBIDDEN)


# ── Property Views ────────────────────────────────────────────────────

class PropertyListCreateView(APIView):
    """
    GET  /api/properties/  — list all of this landlord's properties
    POST /api/properties/  — create a new property
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request):
        landlord = _get_landlord(request)
        props = (
            Property.objects
            .filter(landlord=landlord)
            .prefetch_related("photos", "amenities", "units")
            .order_by("-created_at")
        )
        serializer = PropertyListSerializer(props, many=True)
        return Response(serializer.data)

    def post(self, request):
        landlord   = _get_landlord(request)
        serializer = PropertyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            prop = create_property(landlord, serializer.validated_data)
        except SubscriptionLimitError as e:
            return _handle_limit_error(e)
        return Response(
            PropertyDetailSerializer(prop).data,
            status=status.HTTP_201_CREATED,
        )


class PropertyDetailView(APIView):
    """
    GET    /api/properties/<id>/  — full property detail
    PATCH  /api/properties/<id>/  — update property fields
    DELETE /api/properties/<id>/  — soft delete property and all its units
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request, pk):
        landlord = _get_landlord(request)
        prop     = get_property_or_404(pk, landlord=landlord)
        return Response(PropertyDetailSerializer(prop).data)

    def patch(self, request, pk):
        landlord   = _get_landlord(request)
        prop       = get_property_or_404(pk, landlord=landlord)
        serializer = PropertyUpdateSerializer(prop, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        prop = update_property(prop, serializer.validated_data)
        return Response(PropertyDetailSerializer(prop).data)

    def delete(self, request, pk):
        landlord = _get_landlord(request)
        prop     = get_property_or_404(pk, landlord=landlord)
        prop.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Amenity Views ─────────────────────────────────────────────────────

class PropertyAmenitiesView(APIView):
    """
    GET /api/properties/<id>/amenities/  — list all amenity flags
    PUT /api/properties/<id>/amenities/  — bulk update all amenities
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request, pk):
        landlord = _get_landlord(request)
        prop     = get_property_or_404(pk, landlord=landlord)
        amenities = prop.amenities.all()
        return Response(PropertyAmenitySerializer(amenities, many=True).data)

    def put(self, request, pk):
        landlord   = _get_landlord(request)
        prop       = get_property_or_404(pk, landlord=landlord)
        serializer = AmenitiesBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amenities = set_amenities(prop, serializer.to_amenity_dict())
        return Response(PropertyAmenitySerializer(amenities, many=True).data)


# ── Photo Views ──────────────────────────────────────────────────────

class PropertyPhotosView(APIView):
    """
    GET  /api/properties/<id>/photos/  — list all photos
    POST /api/properties/<id>/photos/  — add a photo URL (after Cloudinary upload)
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request, pk):
        landlord = _get_landlord(request)
        prop     = get_property_or_404(pk, landlord=landlord)
        return Response(PropertyPhotoSerializer(prop.photos.all(), many=True).data)

    def post(self, request, pk):
        landlord   = _get_landlord(request)
        prop       = get_property_or_404(pk, landlord=landlord)
        serializer = PropertyPhotoSerializer(
            data=request.data, context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        try:
            photo = add_photo(
                prop=prop, user=request.user,
                photo_url=d["photo_url"],
                cloudinary_id=d.get("cloudinary_id", ""),
                unit=d.get("unit"),
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PropertyPhotoSerializer(photo).data, status=status.HTTP_201_CREATED)


class PropertyPhotoDeleteView(APIView):
    """DELETE /api/properties/<id>/photos/<photo_id>/"""
    permission_classes = [IsAuthenticated, IsLandlord]

    def delete(self, request, pk, photo_id):
        landlord = _get_landlord(request)
        prop     = get_property_or_404(pk, landlord=landlord)
        try:
            photo = PropertyPhoto.objects.get(pk=photo_id, property=prop)
            photo.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except PropertyPhoto.DoesNotExist:
            return Response({"error": "Photo not found."}, status=status.HTTP_404_NOT_FOUND)


class PhotoReorderView(APIView):
    """PATCH /api/properties/<id>/photos/reorder/ — drag-and-drop reorder"""
    permission_classes = [IsAuthenticated, IsLandlord]

    def patch(self, request, pk):
        landlord   = _get_landlord(request)
        prop       = get_property_or_404(pk, landlord=landlord)
        serializer = PhotoReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reorder_photos(prop, serializer.validated_data["ordered_ids"])
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": "Photos reordered."}, status=status.HTTP_200_OK)


class PropertyUploadSignatureView(APIView):
    """
    GET /api/properties/upload-signature/?type=property_photo|unit_photo
    Rate-limited. Returns short-lived Cloudinary signing credentials.
    """
    permission_classes = [IsAuthenticated, IsLandlord]
    throttle_classes   = [UploadSignatureThrottle]
    VALID_TYPES        = ("property_photo", "unit_photo")

    def get(self, request):
        upload_type = request.query_params.get("type")
        if upload_type not in self.VALID_TYPES:
            return Response(
                {"error": f"type must be one of: {self.VALID_TYPES}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(get_cloudinary_upload_signature(request.user, upload_type))


# ── Penalty Rule Views ────────────────────────────────────────────────

class PropertyPenaltyRuleView(APIView):
    """
    GET   /api/properties/<id>/penalty-rule/  — get property default rule
    PATCH /api/properties/<id>/penalty-rule/  — update property default rule
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request, pk):
        landlord = _get_landlord(request)
        prop     = get_property_or_404(pk, landlord=landlord)
        rule     = get_or_create_property_penalty_rule(prop)
        return Response(PenaltyRuleSerializer(rule).data)

    def patch(self, request, pk):
        landlord   = _get_landlord(request)
        prop       = get_property_or_404(pk, landlord=landlord)
        rule       = get_or_create_property_penalty_rule(prop)
        serializer = PenaltyRuleSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        rule = update_penalty_rule(rule, serializer.validated_data)
        return Response(PenaltyRuleSerializer(rule).data)


# ── Unit Views ────────────────────────────────────────────────────────

class UnitListCreateView(APIView):
    """
    GET  /api/properties/<id>/units/  — list all units for a property
    POST /api/properties/<id>/units/  — add a new unit
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request, pk):
        landlord = _get_landlord(request)
        prop     = get_property_or_404(pk, landlord=landlord)
        return Response(UnitSerializer(prop.units.all(), many=True).data)

    def post(self, request, pk):
        landlord   = _get_landlord(request)
        prop       = get_property_or_404(pk, landlord=landlord)
        serializer = UnitSerializer(
            data=request.data,
            context={"request": request, "property_id": prop.id},
        )
        serializer.is_valid(raise_exception=True)
        try:
            unit = create_unit(landlord, prop, serializer.validated_data)
        except SubscriptionLimitError as e:
            return _handle_limit_error(e)
        return Response(UnitSerializer(unit).data, status=status.HTTP_201_CREATED)


class UnitDetailView(APIView):
    """
    GET    /api/properties/units/<id>/
    PATCH  /api/properties/units/<id>/
    DELETE /api/properties/units/<id>/
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request, pk):
        landlord = _get_landlord(request)
        unit = get_unit_or_404(pk, landlord=landlord)
        return Response(UnitSerializer(unit).data)

    def patch(self, request, pk):
        landlord   = _get_landlord(request)
        unit       = get_unit_or_404(pk, landlord=landlord)
        serializer = UnitSerializer(
            unit, data=request.data, partial=True,
            context={"request": request, "property_id": unit.property_id},
        )
        serializer.is_valid(raise_exception=True)
        unit = update_unit(unit, serializer.validated_data)
        return Response(UnitSerializer(unit).data)

    def delete(self, request, pk):
        landlord = _get_landlord(request)
        unit     = get_unit_or_404(pk, landlord=landlord)
        unit.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UnitPenaltyRuleView(APIView):
    """
    GET   /api/properties/units/<id>/penalty-rule/  — effective rule (unit or property fallback)
    PATCH /api/properties/units/<id>/penalty-rule/  — set unit-level override
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request, pk):
        landlord = _get_landlord(request)
        unit     = get_unit_or_404(pk, landlord=landlord)
        rule     = unit.effective_penalty_rule
        if not rule:
            return Response({"detail": "No penalty rule configured."}, status=404)
        return Response(PenaltyRuleSerializer(rule).data)

    def patch(self, request, pk):
        landlord   = _get_landlord(request)
        unit       = get_unit_or_404(pk, landlord=landlord)
        serializer = PenaltyRuleSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        rule = set_unit_penalty_rule(unit, serializer.validated_data)
        return Response(PenaltyRuleSerializer(rule).data)


# ── Dashboard Summary ─────────────────────────────────────────────────

class PropertyDashboardView(APIView):
    """
    GET /api/properties/dashboard/
    Returns portfolio-level summary for the landlord dashboard:
    total properties, total units, occupancy %, vacant units, setup gaps.
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request):
        landlord = _get_landlord(request)
        props    = Property.objects.filter(landlord=landlord)

        total_properties = props.count()
        total_actual     = sum(p.actual_units for p in props)
        total_occupied   = Unit.objects.filter(
            property__landlord=landlord, status="occupied"
        ).count()
        total_vacant     = Unit.objects.filter(
            property__landlord=landlord, status="vacant"
        ).count()
        total_maintenance= Unit.objects.filter(
            property__landlord=landlord, status="maintenance"
        ).count()
        setup_gaps       = sum(p.setup_gap for p in props)

        return Response({
            "total_properties":    total_properties,
            "total_units":         total_actual,
            "total_occupied":      total_occupied,
            "total_vacant":        total_vacant,
            "total_maintenance":   total_maintenance,
            "overall_occupancy_percent": (
                int((total_occupied / total_actual) * 100) if total_actual else 0
            ),
            "setup_gaps":          setup_gaps,
            "properties":          PropertyListSerializer(props, many=True).data,
        })


# ── Admin Views ───────────────────────────────────────────────────────

class AdminPropertyListView(generics.ListAPIView):
    """GET /api/properties/admin/list/ — paginated list of all properties."""
    serializer_class   = PropertyListSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class   = PropertyPagination

    def get_queryset(self):
        qs = (
            Property.objects_all
            .select_related("landlord__user")
            .prefetch_related("photos", "units")
            .order_by("-created_at")
        )
        county = self.request.query_params.get("county")
        ptype  = self.request.query_params.get("property_type")
        if county: qs = qs.filter(county=county)
        if ptype:  qs = qs.filter(property_type=ptype)
        return qs


class AdminPropertyDetailView(generics.RetrieveAPIView):
    """GET /api/properties/admin/<id>/ — full property detail for admin."""
    serializer_class   = PropertyDetailSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    queryset = Property.objects_all.select_related("landlord__user").prefetch_related(
        "amenities", "photos", "units"
    )
