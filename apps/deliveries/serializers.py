from datetime import date
from decimal import Decimal
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.pricing.services import get_active_price
from apps.registry.models import Plot, WashingStation
from apps.registry.serializers import NameRelatedField

from .models import MAX_DELIVERY_WEIGHT_KG, Delivery


class DeliverySerializer(serializers.ModelSerializer):
    """Full delivery record, used to record a delivery and to read one back."""

    plot = serializers.PrimaryKeyRelatedField(queryset=Plot.objects.select_related("washing_station"))
    washing_station = NameRelatedField(queryset=WashingStation.objects.all())
    weight_kg = serializers.DecimalField(max_digits=6, decimal_places=2)
    delivered_on = serializers.DateField(required=False)
    client_reference = serializers.CharField(max_length=64, required=False, allow_null=True, allow_blank=True)
    plot_code = serializers.CharField(source="plot.plot_code", read_only=True)
    farmer = serializers.IntegerField(source="plot.farmer_id", read_only=True)
    farmer_name = serializers.CharField(source="plot.farmer.full_name", read_only=True)
    season = serializers.CharField(source="price_schedule.season", read_only=True)
    is_exportable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Delivery
        fields = [
            "id",
            "plot",
            "plot_code",
            "farmer",
            "farmer_name",
            "washing_station",
            "weight_kg",
            "grade",
            "delivered_on",
            "client_reference",
            "season",
            "unit_price_rwf",
            "amount_due_rwf",
            "plot_risk_status_at_delivery",
            "is_exportable",
            "recorded_at",
        ]
        read_only_fields = [
            "id",
            "unit_price_rwf",
            "amount_due_rwf",
            "plot_risk_status_at_delivery",
            "recorded_at",
        ]
        # Duplicate client_reference is an idempotent replay handled by the view, not a 400.
        validators: list[Any] = []

    def validate_weight_kg(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("Must be greater than 0.")
        if value > MAX_DELIVERY_WEIGHT_KG:
            raise serializers.ValidationError(f"Must be at most {MAX_DELIVERY_WEIGHT_KG} kg for one delivery.")
        return value

    def validate_delivered_on(self, value: date) -> date:
        if value > timezone.localdate():
            raise serializers.ValidationError("Delivery date cannot be in the future.")
        return value

    def validate_client_reference(self, value: str | None) -> str | None:
        return value.strip() or None if value else None

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        plot: Plot = attrs["plot"]
        station: WashingStation = attrs["washing_station"]
        if plot.washing_station_id != station.pk:
            raise serializers.ValidationError(
                {
                    "washing_station": [
                        f"Plot {plot.plot_code} delivers to {plot.washing_station.name}, not {station.name}."
                    ]
                }
            )
        price_entry = get_active_price(attrs["grade"])
        if price_entry is None:
            raise serializers.ValidationError(
                {"grade": [f"No active price for grade {attrs['grade']}; the station cannot pay for this delivery."]}
            )
        attrs["price_entry"] = price_entry
        return attrs


class DeliveryFeedSerializer(serializers.ModelSerializer):
    """Slim, flat row for the station feed: no nested objects, so pages stay small on 2G."""

    washing_station = serializers.CharField(source="washing_station.name", read_only=True)
    plot_code = serializers.CharField(source="plot.plot_code", read_only=True)
    farmer_name = serializers.CharField(source="plot.farmer.full_name", read_only=True)
    is_exportable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Delivery
        fields = [
            "id",
            "client_reference",
            "washing_station",
            "plot",
            "plot_code",
            "farmer_name",
            "weight_kg",
            "grade",
            "amount_due_rwf",
            "delivered_on",
            "recorded_at",
            "is_exportable",
        ]
        read_only_fields = fields
