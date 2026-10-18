"""Create the F2 access-matrix fixtures (docs/autograding/F2_CONTRACT.md). Safe to run repeatedly.

Every value is copied from the contract. Records are written through the models, not the API:
plots skip register_plot so no risk-check job is queued. Re-running converges existing rows on
the seed values instead of duplicating them.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, UserProfile
from apps.deliveries.services import find_replay, record_delivery
from apps.pricing.services import get_active_price
from apps.registry.models import Farmer, Plot, Sector, WashingStation

PASSWORD = "GraderPass123!"

# username, role, washing station
USERS = [
    ("field_agent_user", Role.FIELD_AGENT, "Nyaruguru"),
    ("exporter_user", Role.EXPORTER_PARTNER, None),
    ("auditor_user", Role.COMPLIANCE_AUDITOR, None),
]

FARMER = {
    "full_name": "Uwimana Béatrice",
    "national_id": "1198770123456789",
    "member_number": "KWA-F-SEED-01",
    # Not in the contract; invented so it cannot collide with the F1 flow's +250780000000.
    "phone": "+250788999001",
}

# plot_code, sector, washing station, latitude, longitude
PLOTS = [
    ("KWA-SEED-K1", "Kigoma", "Nyaruguru", "-2.540000", "29.710000"),
    ("KWA-SEED-K2", "Kigoma", "Nyaruguru", "-2.660000", "29.790000"),
    ("KWA-SEED-M1", "Mbazi", "Kamonyi", "-2.510000", "29.520000"),
    ("KWA-SEED-M2", "Mbazi", "Kamonyi", "-2.900000", "29.900000"),
]
PLOT_AREA_HECTARES = Decimal("0.50")

# client_reference, plot_code; each delivery is recorded at its plot's washing station.
DELIVERIES = [
    ("seed-rbac-K1", "KWA-SEED-K1"),
    ("seed-rbac-M1", "KWA-SEED-M1"),
]
DELIVERY_WEIGHT_KG = Decimal("38.50")
DELIVERY_GRADE = "A"
DELIVERED_ON = date(2026, 3, 14)


class Command(BaseCommand):
    help = "Create the F2 role users, seed farmer, four fixture plots and two deliveries."

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        for username, role, station in USERS:
            self.seed_user(username, role, station)
        farmer = self.seed_farmer()
        plots = {code: self.seed_plot(farmer, code, *rest) for code, *rest in PLOTS}
        for client_reference, plot_code in DELIVERIES:
            self.seed_delivery(plots[plot_code], client_reference)
        self.stdout.write(
            self.style.SUCCESS(
                f"RBAC fixtures ready: {len(USERS)} users, farmer {farmer.member_number}, "
                f"{len(PLOTS)} plots, {len(DELIVERIES)} deliveries."
            )
        )

    def seed_user(self, username: str, role: str, station_name: str | None) -> None:
        user, _ = User.objects.get_or_create(username=username)
        # Reset on every run so a changed password or a deactivated account cannot break grading.
        user.set_password(PASSWORD)
        user.is_active = True
        user.save()
        station = WashingStation.objects.get(name=station_name) if station_name else None
        UserProfile.objects.update_or_create(user=user, defaults={"role": role, "washing_station": station})

    def seed_farmer(self) -> Farmer:
        # member_number is the farmer's natural key. The F1 contract flow registers the same
        # person and national ID under KWA-F-0417; that record is left alone, so the F1 flow
        # still creates and replays its own farmer after seeding.
        farmer = Farmer.objects.filter(member_number=FARMER["member_number"]).first() or Farmer()
        phone_owner = Farmer.objects.filter(phone=FARMER["phone"]).exclude(pk=farmer.pk).first()
        if phone_owner:
            raise CommandError(f"Seed phone {FARMER['phone']} already belongs to farmer {phone_owner.pk}.")
        for field, value in FARMER.items():
            setattr(farmer, field, value)
        farmer.save()
        return farmer

    def seed_plot(self, farmer: Farmer, code: str, sector: str, station: str, lat: str, lon: str) -> Plot:
        # update_or_create, not register_plot: no on_commit hook, so no risk-check job is queued.
        plot, _ = Plot.objects.update_or_create(
            plot_code=code,
            defaults={
                "farmer": farmer,
                "sector": Sector.objects.get(name=sector),
                "washing_station": WashingStation.objects.get(name=station),
                "latitude": Decimal(lat),
                "longitude": Decimal(lon),
                "area_hectares": PLOT_AREA_HECTARES,
            },
        )
        return plot

    def seed_delivery(self, plot: Plot, client_reference: str) -> None:
        # An existing delivery is kept as is: its price is a snapshot of the amount due recorded.
        if find_replay(plot.washing_station.name, client_reference):
            return
        price = get_active_price(DELIVERY_GRADE, on=DELIVERED_ON)
        if price is None:
            raise CommandError(f"No active price for grade {DELIVERY_GRADE}; cannot record seed deliveries.")
        record_delivery(
            plot=plot,
            washing_station=plot.washing_station,
            weight_kg=DELIVERY_WEIGHT_KG,
            grade=DELIVERY_GRADE,
            price_entry=price,
            delivered_on=DELIVERED_ON,
            client_reference=client_reference,
        )
