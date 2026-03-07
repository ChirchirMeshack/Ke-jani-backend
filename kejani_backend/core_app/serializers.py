from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User


class LoginSerializer(serializers.Serializer):

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):

        email = data.get("email")
        password = data.get("password")

        # authenticate user
        user = authenticate(username=email, password=password)

        if not user:
            raise serializers.ValidationError("Invalid email or password")

        if not user.is_active:
            raise serializers.ValidationError("Account disabled")

        roles = [r.role.role_name for r in user.user_roles.all()]

        # -------- APPROVAL CHECKS -------- #

        # Project Manager must be approved by admin
        if "project_manager" in roles:
            pm_profile = getattr(user, "pm_profile", None)
            if pm_profile and pm_profile.status != "approved":
                raise serializers.ValidationError(
                    "Project manager account not approved yet"
                )

        # Landlord must be approved by admin
        if "landlord" in roles:
            landlord_profile = getattr(user, "landlord_profile", None)
            if landlord_profile and landlord_profile.status != "approved":
                raise serializers.ValidationError(
                    "Landlord account not approved yet"
                )

        # Tenant created by landlord or PM → allowed to login
        # (no approval restriction)

        # generate tokens
        refresh = RefreshToken.for_user(user)

        return {
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "roles": roles,
            "access_token": str(refresh.access_token),
            "refresh_token": str(refresh),
        }



        