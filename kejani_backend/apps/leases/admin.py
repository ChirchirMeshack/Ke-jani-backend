from django.contrib import admin
from .models import Lease


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    list_display = [
        "tenant", "unit", "lease_start", "lease_end",
        "monthly_rent", "status", "days_remaining_display",
    ]
    list_filter   = ["status"]
    search_fields = ["tenant__user__email", "unit__unit_number", "unit__property__name"]
    readonly_fields = ["created_at", "updated_at", "previous_lease"]

    def days_remaining_display(self, obj):
        d = obj.days_remaining
        if d < 0:
            return f"Expired {abs(d)} days ago"
        if d <= 30:
            return f"⚠ {d} days"
        return f"{d} days"
    days_remaining_display.short_description = "Days Remaining"
