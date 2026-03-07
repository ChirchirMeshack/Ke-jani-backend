from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import LoginSerializer
from .models import Role, User, Landlord, Tenant
from rest_framework.permissions import IsAuthenticated


class LoginView(APIView):

    permission_classes = []

    def post(self, request):

        serializer = LoginSerializer(data=request.data)

        if serializer.is_valid():
            return Response(serializer.validated_data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class CreateUserView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        user = request.user
        role_requested = request.data.get("role")

        username = request.data.get("username")
        email = request.data.get("email")

        if not role_requested:
            return Response(
                {"error": "Role is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # -----------------------------
        # CREATE LANDLORD
        # -----------------------------
        if role_requested == "landlord":

            if not (user.is_admin or user.is_project_manager):
                return Response(
                    {"error": "Only admin or project manager can create landlords"},
                    status=status.HTTP_403_FORBIDDEN
                )

            landlord_role = Role.objects.get(role_name="landlord")

            new_user, token = User.objects.invite_user(
                username=username,
                email=email,
                role_obj=landlord_role,
                created_by=user
            )

            Landlord.objects.create(
                user=new_user,
                created_by=user,
                phone=request.data.get("phone"),
                id_number=request.data.get("id_number"),
                number_of_properties=request.data.get("number_of_properties")
            )

            return Response({
                "message": "Landlord created and awaiting admin approval",
                "invitation_token": token
            })

        # -----------------------------
        # CREATE TENANT
        # -----------------------------
        elif role_requested == "tenant":

            if not (user.is_project_manager or user.is_landlord):
                return Response(
                    {"error": "Only landlord or project manager can create tenants"},
                    status=status.HTTP_403_FORBIDDEN
                )

            tenant_role = Role.objects.get(role_name="tenant")

            new_user, token = User.objects.invite_user(
                username=username,
                email=email,
                role_obj=tenant_role,
                created_by=user
            )

            Tenant.objects.create(
                user=new_user,
                landlord=user if user.is_landlord else None,
                phone=request.data.get("phone"),
                id_number=request.data.get("id_number"),
                emergency_contact=request.data.get("emergency_contact"),
                unit_id=request.data.get("unit_id"),
            )

            return Response({
                "message": "Tenant created successfully",
                "invitation_token": token
            })

        return Response(
            {"error": "Invalid role"},
            status=status.HTTP_400_BAD_REQUEST
        )
