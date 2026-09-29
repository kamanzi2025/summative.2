"""Load demo farmers, plots and deliveries for local exploration. Safe to run repeatedly.

Reference data (sectors, the Nyaruguru and Kamonyi stations, the active price schedule) comes
from data migrations, so it exists on every database after `migrate`.
"""

from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.deliveries.services import record_delivery
from apps.pricing.services import get_active_price
from apps.registry.models import Farmer, Plot, RiskStatus, Sector, WashingStation

FARMERS = [
    ("KWA-F-DEMO-01", "Mukamana Claudine", "+250788100001", "1198070000000101"),
    ("KWA-F-DEMO-02", "Habimana Jean Bosco", "+250788100002", "1197580000000202"),
    ("KWA-F-DEMO-03", "Nyirahabimana Esther", "+250728100003", None),
]

# plot_code, farmer member_number, sector, station, lat, lon, area, risk_status
PLOTS = [
    ("KWA-P-DEMO-01", "KWA-F-DEMO-01", "Kigoma", "Nyaruguru", "-2.541200", "29.712300", "0.35", RiskStatus.CLEAR),
    ("KWA-P-DEMO-02", "KWA-F-DEMO-02", "Kigoma", "Nyaruguru", "-2.655000", "29.781000", "0.60", RiskStatus.PENDING),
    ("KWA-P-DEMO-03", "KWA-F-DEMO-03", "Mbazi", "Kamonyi", "-2.512000", "29.521000", "0.25", RiskStatus.FLAGGED),
]


class Command(BaseCommand):
    help = "Create demo farmers, plots (with preset risk statuses) and deliveries."

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        farmers = {}
        for member_number, name, phone, national_id in FARMERS:
            farmers[member_number], _ = Farmer.objects.get_or_create(
                member_number=member_number,
                defaults={"full_name": name, "phone": phone, "national_id": national_id, "cooperative": "Huye"},
            )

        for code, member, sector, station, lat, lon, area, risk in PLOTS:
            # Created directly (not via register_plot) so demo data never needs a worker.
            plot, created = Plot.objects.get_or_create(
                plot_code=code,
                defaults={
                    "farmer": farmers[member],
                    "sector": Sector.objects.get(name=sector),
                    "washing_station": WashingStation.objects.get(name=station),
                    "latitude": Decimal(lat),
                    "longitude": Decimal(lon),
                    "area_hectares": Decimal(area),
                    "risk_status": risk,
                },
            )
            if not created:
                continue
            for i, (weight, grade) in enumerate([("38.50", "A"), ("22.00", "B")], start=1):
                price = get_active_price(grade)
                if price is None:
                    self.stderr.write(f"No active price for grade {grade}; skipping demo delivery.")
                    continue
                record_delivery(
                    plot=plot,
                    washing_station=plot.washing_station,
                    weight_kg=Decimal(weight),
                    grade=grade,
                    price_entry=price,
                    client_reference=f"demo-{code}-{i}",
                )

        self.stdout.write(
            self.style.SUCCESS(f"Demo data ready: {Farmer.objects.count()} farmers, {Plot.objects.count()} plots.")
        )
