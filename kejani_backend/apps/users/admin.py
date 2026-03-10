from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    AccessAuditLog,
    EmailVerificationToken,
    PMInvitation,
    PasswordResetToken,
    TenantInvitation,
    User,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'email', 'first_name', 'last_name', 'role',
        'approval_status', 'email_verified', 'is_active', 'is_demo',
    )
    list_filter = ('role', 'approval_status', 'email_verified', 'is_active', 'is_demo')
    search_fields = ('email', 'first_name', 'last_name', 'phone')
    ordering = ('-created_at',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'phone', 'uuid')}),
        ('Role & Status', {'fields': ('role', 'approval_status', 'email_verified', 'phone_verified')}),
        ('Flags', {'fields': ('is_first_login', 'is_demo')}),
        ('Security', {'fields': ('last_login_ip', 'last_login')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Soft Delete', {'fields': ('deleted_at',)}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 'username', 'first_name', 'last_name',
                'role', 'password1', 'password2',
            ),
        }),
    )

    readonly_fields = ('uuid', 'last_login_ip', 'last_login')


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'is_used', 'created_at')
    list_filter = ('is_used',)
    search_fields = ('user__email',)


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'is_used', 'expires_at', 'created_at')
    list_filter = ('is_used',)
    search_fields = ('user__email',)


@admin.register(PMInvitation)
class PMInvitationAdmin(admin.ModelAdmin):
    list_display = (
        'invited_email', 'invited_name', 'invited_by',
        'status', 'commission_rate', 'expires_at',
    )
    list_filter = ('status',)
    search_fields = ('invited_email', 'invited_name')


@admin.register(TenantInvitation)
class TenantInvitationAdmin(admin.ModelAdmin):
    list_display = (
        'invited_email', 'invited_name', 'invited_by',
        'property_name', 'unit_number', 'status', 'expires_at',
    )
    list_filter = ('status',)
    search_fields = ('invited_email', 'invited_name', 'property_name')


@admin.register(AccessAuditLog)
class AccessAuditLogAdmin(admin.ModelAdmin):
    list_display = ('event', 'user', 'ip_address', 'role', 'created_at')
    list_filter = ('event', 'role')
    search_fields = ('user__email', 'ip_address')
    readonly_fields = ('event', 'user', 'ip_address', 'role', 'details', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
