"""Seed the active 2026A price schedule so deliveries can be priced on a fresh database.

Prices are illustrative placeholders for the MVP; the cooperative replaces them with the
season's announced farm-gate prices through the admin.
"""

import datetime
from decimal import Decimal

from django.db import migrations

SEASON = "2026A"
PRICES = {"A": Decimal("760.00"), "B": Decimal("500.00"), "C": Decimal("300.00")}


def seed(apps, schema_editor):
    PriceSchedule = apps.get_model("pricing", "PriceSchedule")
    PriceEntry = apps.get_model("pricing", "PriceEntry")
    if PriceSchedule.objects.filter(season=SEASON).exists():
        return
    schedule = PriceSchedule.objects.create(season=SEASON, effective_from=datetime.date(2026, 3, 1), is_active=True)
    PriceEntry.objects.bulk_create(
        PriceEntry(schedule=schedule, grade=grade, price_per_kg_rwf=price) for grade, price in PRICES.items()
    )


def unseed(apps, schema_editor):
    apps.get_model("pricing", "PriceSchedule").objects.filter(season=SEASON).delete()


class Migration(migrations.Migration):
    dependencies = [("pricing", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
