import re
from decimal import Decimal
from typing import Any

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import (
    MAX_PLOT_AREA_HECTARES,
    RWANDA_LAT_MAX,
    RWANDA_LAT_MIN,
    RWANDA_LON_MAX,
    RWANDA_LON_MIN,
    Farmer,
    Plot,
    RiskCheckAttempt,
    Sector,
    WashingStation,
)
from .services import register_farmer, register_plot
from .validators import normalise_rwandan_phone

_NATIONAL_ID = re.compile(r"^\d{16}$")


class RwandanPhoneField(serializers.CharField):
    """Accepts +2507XXXXXXXX, 2507XXXXXXXX or 07XXXXXXXX and stores E.164 (+2507XXXXXXXX).

    Normalising here (not in validate_phone) means the uniqueness check compares normalised
    numbers, so "0780000000" and "+250780000000" are recognised as the same farmer.
    """

    def to_internal_value(self, data: Any) -> str:
        phone = normalise_rwandan_phone(super().to_internal_value(data))
        if phone is None:
            raise serializers.ValidationError("Enter a Rwandan mobile number such as +250780000000 or 0780000000.")
        return phone


class NameRelatedField(serializers.SlugRelatedField):
    """Refers to a sector or washing station by its name, e.g. "Nyaruguru"."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(slug_field="name", **kwargs)

    def to_internal_value(self, data: Any) -> Any:
        try:
            return self.get_queryset().get(name__iexact=str(data).strip())
        except (self.get_queryset().model.DoesNotExist, TypeError, ValueError):
            self.fail("does_not_exist", slug_name=self.slug_field, value=str(data))


class SectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sector
        fields = ["id", "name", "district"]


class WashingStationSerializer(serializers.ModelSerializer):
    sector = serializers.CharField(source="sector.name", read_only=True)

    class Meta:
        model = WashingStation
        fields = ["id", "name", "code", "sector"]


class FarmerSerializer(serializers.ModelSerializer):
    phone = RwandanPhoneField(
        max_length=20,
        validators=[UniqueValidator(Farmer.objects.all(), message="A farmer with this phone number already exists.")],
    )
    national_id = serializers.CharField(max_length=16, required=False, allow_null=True, allow_blank=True)
    home_station = NameRelatedField(queryset=WashingStation.objects.all(), required=False, allow_null=True)

    class Meta:
        model = Farmer
        fields = [
            "id",
            "full_name",
            "member_number",
            "cooperative",
            "phone",
            "national_id",
            "home_station",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_full_name(self, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise serializers.ValidationError("Enter the farmer's full name.")
        return value

    def validate_national_id(self, value: str | None) -> str | None:
        if not value:
            return None
        if not _NATIONAL_ID.match(value):
            raise serializers.ValidationError("National ID must be exactly 16 digits.")
        if Farmer.objects.filter(national_id=value).exists():
            raise serializers.ValidationError("A farmer with this national ID already exists.")
        return value

    def create(self, validated_data: dict[str, Any]) -> Farmer:
        return register_farmer(validated_data)


class PlotSerializer(serializers.ModelSerializer):
    sector = NameRelatedField(queryset=Sector.objects.all())
    washing_station = NameRelatedField(queryset=WashingStation.objects.all())
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, coerce_to_string=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, coerce_to_string=True)
    area_hectares = serializers.DecimalField(
        max_digits=8,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        max_value=MAX_PLOT_AREA_HECTARES,
    )
    requires_manual_review = serializers.BooleanField(read_only=True)

    class Meta:
        model = Plot
        fields = [
            "id",
            "farmer",
            "plot_code",
            "label",
            "sector",
            "washing_station",
            "latitude",
            "longitude",
            "area_hectares",
            "risk_status",
            "risk_checked_at",
            "requires_manual_review",
            "created_at",
        ]
        read_only_fields = ["id", "risk_status", "risk_checked_at", "created_at"]

    def validate_latitude(self, value: Decimal) -> Decimal:
        if not RWANDA_LAT_MIN <= value <= RWANDA_LAT_MAX:
            raise serializers.ValidationError(f"Latitude must be inside Rwanda ({RWANDA_LAT_MIN} to {RWANDA_LAT_MAX}).")
        return value

    def validate_longitude(self, value: Decimal) -> Decimal:
        if not RWANDA_LON_MIN <= value <= RWANDA_LON_MAX:
            raise serializers.ValidationError(
                f"Longitude must be inside Rwanda ({RWANDA_LON_MIN} to {RWANDA_LON_MAX})."
            )
        return value

    def create(self, validated_data: dict[str, Any]) -> Plot:
        return register_plot(validated_data)


class RiskCheckAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskCheckAttempt
        fields = [
            "attempt_number",
            "outcome",
            "started_at",
            "finished_at",
            "duration_ms",
            "error_message",
            "task_id",
        ]
        read_only_fields = fields
