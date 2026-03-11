from django.contrib import admin
from django.utils.html import format_html
from .models import Property, Unit, PropertyAmenity, PropertyPhoto, PenaltyRule


class UnitInline(admin.TabularInline):
    model  = Unit
    extra  = 0
    fields = ["unit_number", "bedrooms", "bathrooms", "rent_amount", "status"]
    readonly_fields = ["status"]


class AmenityInline(admin.TabularInline):
    model  = PropertyAmenity
    extra  = 0
    fields = ["amenity_name", "available"]


class PenaltyRuleInline(admin.TabularInline):
    model  = PenaltyRule
    extra  = 0
    fields = ["penalty_type", "penalty_value", "grace_period_days", "effective_from"]


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display   = [
        "name", "landlord", "property_type", "county", "area",
        "declared_units", "actual_units", "occupancy_display", "is_active",
    ]
    list_filter    = ["property_type", "county", "listing_type", "is_active", "management_mode"]
    search_fields  = ["name", "landlord__user__email", "area", "estate"]
    readonly_fields= ["actual_units", "created_at", "updated_at"]
    inlines        = [UnitInline, AmenityInline, PenaltyRuleInline]
    ordering       = ["-created_at"]

    def occupancy_display(self, obj):
        pct   = obj.occupancy_percent
        color = "green" if pct >= 80 else "orange" if pct >= 50 else "red"
        return format_html('<span style="color:{}">{} %</span>', color, pct)
    occupancy_display.short_description = "Occupancy"


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display  = ["unit_number", "property", "bedrooms", "rent_amount", "status", "deleted_at"]
    list_filter   = ["status", "furnished", "has_parking"]
    search_fields = ["unit_number", "property__name", "property__landlord__user__email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(PenaltyRule)
class PenaltyRuleAdmin(admin.ModelAdmin):
    list_display = ["__str__", "penalty_type", "penalty_value", "grace_period_days", "effective_from"]
    list_filter  = ["penalty_type"]
