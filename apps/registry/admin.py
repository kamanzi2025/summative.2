from django.contrib import admin

from .models import Farmer, Plot, RiskCheckAttempt, Sector, WashingStation


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ["name", "district"]


@admin.register(WashingStation)
class WashingStationAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "sector"]


@admin.register(Farmer)
class FarmerAdmin(admin.ModelAdmin):
    list_display = ["full_name", "member_number", "phone", "cooperative", "created_at"]
    search_fields = ["full_name", "member_number", "phone"]


class RiskCheckAttemptInline(admin.TabularInline):
    model = RiskCheckAttempt
    extra = 0
    readonly_fields = ["attempt_number", "outcome", "started_at", "finished_at", "duration_ms", "error_message"]


@admin.register(Plot)
class PlotAdmin(admin.ModelAdmin):
    list_display = ["plot_code", "farmer", "sector", "washing_station", "risk_status", "risk_checked_at"]
    list_filter = ["risk_status", "washing_station", "sector"]
    search_fields = ["plot_code", "farmer__full_name"]
    inlines = [RiskCheckAttemptInline]
