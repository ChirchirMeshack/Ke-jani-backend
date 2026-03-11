from rest_framework import views, generics, permissions, status
from rest_framework.response import Response

from .models import SubscriptionPlan
from .serializers import SubscriptionPlanSerializer, SubscriptionSerializer
from .services import get_user_subscription


class MySubscriptionView(views.APIView):
    """
    Retrieve the current authenticated user's active subscription.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        sub = get_user_subscription(request.user)
        if not sub:
            return Response(
                {"detail": "No subscription found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )
            
        serializer = SubscriptionSerializer(sub)
        return Response(serializer.data)


class AvailablePlansView(generics.ListAPIView):
    """
    Publicly list active plans, filterable by `plan_type`
    e.g., ?type=landlord  or ?type=property_manager
    """
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = SubscriptionPlan.objects.filter(is_active=True)
        plan_type = self.request.query_params.get('type')
        if plan_type:
            qs = qs.filter(plan_type=plan_type)
        return qs
