from django.contrib import admin
from .models import PropertyManager, PmServiceArea, PmAssignmentRequest, CommissionRecord


class PmServiceAreaInline(admin.TabularInline):
    model  = PmServiceArea
    extra  = 0
    fields = ["county", "area"]


@admin.register(PropertyManager)
class PropertyManagerAdmin(admin.ModelAdmin):
    list_display  = [
        "user", "approval_status", "subscription_tier",
        "commission_rate", "is_searchable", "units_managed_display", "deleted_at",
    ]
    list_filter   = ["approval_status", "subscription_tier", "is_searchable"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "id_number"]
    readonly_fields = ["created_at", "updated_at", "approved_at", "onboarding_completed_at"]
    inlines       = [PmServiceAreaInline]

    def units_managed_display(self, obj):
        return obj.total_units_managed
    units_managed_display.short_description = "Units Managed"


@admin.register(PmAssignmentRequest)
class PmAssignmentRequestAdmin(admin.ModelAdmin):
    list_display  = ["property", "pm", "landlord", "status", "commission_rate", "created_at"]
    list_filter   = ["status"]
    search_fields = ["property__name", "pm__user__email", "landlord__user__email", "invite_email"]
    readonly_fields = ["created_at", "updated_at", "invite_token"]


@admin.register(CommissionRecord)
class CommissionRecordAdmin(admin.ModelAdmin):
    list_display  = ["pm", "property", "period", "commission_amount", "status", "paid_at"]
    list_filter   = ["status"]
    search_fields = ["pm__user__email", "property__name"]
    readonly_fields = ["created_at", "updated_at", "commission_amount"]
