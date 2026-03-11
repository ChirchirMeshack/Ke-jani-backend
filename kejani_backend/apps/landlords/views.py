from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.pagination import PageNumberPagination

# Using our custom permission classes assuming they exist in core.permissions
from core.permissions import IsLandlord, IsAdmin
from .models import Landlord
from .serializers import (
    LandlordProfileSerializer,
    LandlordProfileStepSerializer,
    LandlordBasicUpdateSerializer,
    AdminLandlordListSerializer,
)
from .services import (
    complete_profile_step,
    get_landlord_or_404,
    get_cloudinary_upload_signature,
)


class UploadSignatureThrottle(UserRateThrottle):
    """
    Limits upload signature requests to 10 per minute per user.
    Prevents abuse of the Cloudinary signing endpoint.
    """
    scope = 'upload_signature'


class LandlordAdminPagination(PageNumberPagination):
    """Pagination for admin landlord list — 20 per page."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class LandlordProfileView(APIView):
    """
    GET /api/landlords/profile/

    Returns the current landlord's full profile + onboarding progress.
    This is the first call the frontend makes after login for landlord users.
    The onboarding_progress.current_step tells the wizard which step to show.
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request):
        landlord = get_landlord_or_404(request.user)  # includes select_related + prefetch
        return Response(LandlordProfileSerializer(landlord, context={'request': request}).data)


class LandlordProfileStepView(APIView):
    """
    POST /api/landlords/onboarding/step/profile/

    Handles Step 1 of the onboarding wizard:
    - Saves ID copy URLs (uploaded directly to Cloudinary by frontend)
    - Saves avatar URL (optional)
    - Confirms id_number (pre-filled, editable)
    - Sets subscription_tier → creates trial subscription (stub)
    - Records T&C acceptance timestamp
    - Marks profile step + mpesa step if complete

    M-Pesa account is added via POST /api/banking/mpesa/ FIRST,
    then this endpoint checks if it exists and marks the mpesa step.
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def post(self, request):
        landlord   = get_landlord_or_404(request.user)
        serializer = LandlordProfileStepSerializer(
            data=request.data,
            context={'request': request},  # needed for UUID validation in serializer
        )
        serializer.is_valid(raise_exception=True)
        landlord = complete_profile_step(landlord, serializer.validated_data)

        return Response({
            'message':            'Profile step submitted successfully.',
            'onboarding_progress': landlord.onboarding_progress,
            'next_step':           landlord.onboarding_progress['current_step'],
        })


class LandlordBasicUpdateView(APIView):
    """
    PATCH /api/landlords/profile/update/
    Updates basic profile fields from the Settings page (post-onboarding).
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def patch(self, request):
        serializer = LandlordBasicUpdateSerializer(
            data=request.data, context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user
        if 'first_name' in data: user.first_name = data['first_name']
        if 'last_name'  in data: user.last_name  = data['last_name']
        if 'phone'      in data: user.phone      = data['phone']
        user.save()

        landlord = get_landlord_or_404(user)
        if 'avatar_url' in data:
            landlord.avatar_url = data['avatar_url']
            landlord.save(update_fields=['avatar_url'])

        return Response({
            'message': 'Profile updated successfully.',
            'profile': LandlordProfileSerializer(landlord, context={'request': request}).data,
        })


class CloudinaryUploadSignatureView(APIView):
    """
    GET /api/landlords/upload-signature/?type=id_front|id_back|avatar

    Returns short-lived credentials for direct-to-Cloudinary upload.
    Rate limited to 10 requests per minute per user.

    Frontend flow:
    1. Call this endpoint to get { signature, timestamp, api_key, folder, cloud_name }
    2. POST file directly to Cloudinary using those credentials
    3. Cloudinary returns { secure_url }
    4. Send secure_url to POST /api/landlords/onboarding/step/profile/
    """
    permission_classes = [IsAuthenticated, IsLandlord]
    throttle_classes   = [UploadSignatureThrottle]

    VALID_UPLOAD_TYPES = ('id_front', 'id_back', 'avatar')

    def get(self, request):
        upload_type = request.query_params.get('type')
        if upload_type not in self.VALID_UPLOAD_TYPES:
            return Response(
                {'error': f'type must be one of: {self.VALID_UPLOAD_TYPES}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(get_cloudinary_upload_signature(request.user, upload_type))


class LandlordOnboardingProgressView(APIView):
    """
    GET /api/landlords/onboarding/progress/
    Lightweight endpoint — frontend polls after each wizard step to refresh state.
    """
    permission_classes = [IsAuthenticated, IsLandlord]

    def get(self, request):
        landlord = get_landlord_or_404(request.user)
        return Response(landlord.onboarding_progress)


# ── Admin Views ───────────────────────────────────────────────────────────

class AdminLandlordListView(generics.ListAPIView):
    """
    GET /api/landlords/admin/list/
    Paginated list of all landlords for admin review.
    Filter by: ?approval_status=pending|approved|rejected|suspended
               ?tier=solo|starter|growth|professional|enterprise
    """
    serializer_class   = AdminLandlordListSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class   = LandlordAdminPagination

    def get_queryset(self):
        qs = (
            Landlord.objects_all  # see all including soft-deleted for admin
            .select_related('user', 'approved_by')
            .order_by('-created_at')
        )
        approval_status = self.request.query_params.get('approval_status')
        tier            = self.request.query_params.get('tier')

        if approval_status:
            valid = ['pending', 'approved', 'rejected', 'suspended']
            if approval_status in valid:
                qs = qs.filter(user__approval_status=approval_status)

        if tier:
            qs = qs.filter(subscription_tier=tier)

        return qs


class AdminLandlordDetailView(generics.RetrieveAPIView):
    """
    GET /api/landlords/admin/<id>/
    Full profile of one landlord for admin review screen.
    Shows ID copy links so admin can verify identity before approving.
    """
    serializer_class   = AdminLandlordListSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    queryset = Landlord.objects_all.select_related('user', 'approved_by').all()
