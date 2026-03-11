from django.contrib import admin
from .models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = [
        "user", "id_number", "current_unit_display",
        "payment_preference", "has_changed_password", "deleted_at",
    ]
    list_filter   = ["payment_preference", "notification_preference", "has_changed_password"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "id_number"]
    readonly_fields = ["created_at", "updated_at", "onboarding_completed_at"]

    def current_unit_display(self, obj):
        unit = obj.current_unit
        return str(unit) if unit else "—"
    current_unit_display.short_description = "Current Unit"
