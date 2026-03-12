from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Allow access only to admin users."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'admin'
        )


class IsLandlord(BasePermission):
    """Allow access only to approved landlords."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'landlord'
            and request.user.approval_status == 'approved'
        )


class IsPropertyManager(BasePermission):
    """Allow access only to approved property managers."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'property_manager'
            and request.user.approval_status == 'approved'
        )


class IsTenant(BasePermission):
    """Allow access only to tenants."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'tenant'
        )


class IsLandlordOrPropertyManager(BasePermission):
    """Allow access to approved landlords or property managers."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return (
            request.user.role in ('landlord', 'property_manager')
            and request.user.approval_status == 'approved'
        )


class IsAdminOrLandlord(BasePermission):
    """Allow access to admins or approved landlords."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role == 'admin':
            return True
        return (
            request.user.role == 'landlord'
            and request.user.approval_status == 'approved'
        )


class IsAdminOrLandlordOrPM(BasePermission):
    """Allow access to admins, approved landlords, or approved PMs."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role == 'admin':
            return True
        return (
            request.user.role in ('landlord', 'property_manager')
            and request.user.approval_status == 'approved'
        )
