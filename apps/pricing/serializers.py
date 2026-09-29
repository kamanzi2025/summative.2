from rest_framework import serializers

from .models import PriceEntry, PriceSchedule


class PriceEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceEntry
        fields = ["grade", "price_per_kg_rwf"]


class PriceScheduleSerializer(serializers.ModelSerializer):
    currency = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()
    prices = PriceEntrySerializer(source="entries", many=True)

    class Meta:
        model = PriceSchedule
        fields = ["id", "season", "effective_from", "currency", "unit", "prices"]

    def get_currency(self, obj: PriceSchedule) -> str:
        return "RWF"

    def get_unit(self, obj: PriceSchedule) -> str:
        return "kg"
