from django.contrib import admin

from .models import PriceEntry, PriceSchedule


class PriceEntryInline(admin.TabularInline):
    model = PriceEntry
    extra = 0


@admin.register(PriceSchedule)
class PriceScheduleAdmin(admin.ModelAdmin):
    list_display = ["season", "effective_from", "is_active"]
    list_filter = ["is_active", "season"]
    inlines = [PriceEntryInline]
