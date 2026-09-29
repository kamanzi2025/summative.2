from django.contrib import admin

from .models import Delivery


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "washing_station",
        "plot",
        "weight_kg",
        "grade",
        "amount_due_rwf",
        "plot_risk_status_at_delivery",
        "recorded_at",
    ]
    list_filter = ["washing_station", "grade", "plot_risk_status_at_delivery"]
    list_select_related = ["washing_station", "plot"]
    readonly_fields = ["unit_price_rwf", "amount_due_rwf", "plot_risk_status_at_delivery", "recorded_at"]
