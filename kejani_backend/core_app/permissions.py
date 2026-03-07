from rest_framework import permissions
from .models import UserRole,Permission,ROlePermission




class HasSpecificPermission(permissions.BasePermission):
    """
    Generic permission checker using permission_name string.
    View must set: permission_name = "view_properties"(or similar)
    """

    def  has_permission(self,request,view):
        if not request.user_is_authenticed:
            return False

        if self.permission_name is  None:
            return  True   #fallback - better to always specify in production

        return Permission.objects.filter(
            permissions_name = self.permission_name,
            rOlepermission__role__userrole__user=request.user
        ).exists()      



class IsLandlord(permissions.BasePermission):
    def has_permission(self,request, view):
        return request.user.is_landlord





class IsPropertManager(permissions.BasePermission):
    def has_permission(self,request,view):
        return request.user.is_property_manager



class IsTenant(permissions.BasePermission):
    def has_permission(self,request,view):
        return request.user.is_tenant





class CanManageProperty(permissions.BasePermission):
    """
    Landlord owns it directly.
    Property Manager can manage if assigned to the owing landlord
    """

    def has_object_permission(self,request,view,obj):
        user = request.user
      

    landlord = getattr(obj, "landlord",None)

    if landlord is None:
        return False

    if    user.is_landlord:
        return user.landlord_profile == landlord


    if user.is_property_manager:
        return user.managed_by == landlord

    return False




class  CanAccessTenantData(permissions.BasePermission):
    """
    For viewing/editing-specific data(lease,tickets,payments,etc)
    
    """
    def has_object_permission(self,request,view,obj):
        user = request.user
        tenant = getattr(obj,"tenant",None) or getattr(tenant,"unit",None)
        
        if unit and unit.property.landlord:
            landlord = unit.property.landlord
            if user.is_landlord and user.landlord_profile ==landlord:
                return True
            if user.is_property_manager and user.manageger_profile.managed_by == landlord:
                return True

        return False        


            





