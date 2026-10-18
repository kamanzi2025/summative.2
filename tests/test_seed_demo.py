from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.deliveries.models import Delivery
from apps.pricing.models import PriceEntry, PriceSchedule


class SeedDemoPricingTests(TestCase):
    def test_seeded_deliveries_use_one_date_for_price_and_delivery(self):
        delivery_date = date(2026, 3, 15)
        current_schedule = PriceSchedule.objects.get(is_active=True)
        future_schedule = PriceSchedule.objects.create(
            season=current_schedule.season,
            effective_from=date(2026, 3, 16),
            is_active=True,
        )
        for grade, price in (("A", "999.00"), ("B", "888.00")):
            PriceEntry.objects.create(schedule=future_schedule, grade=grade, price_per_kg_rwf=Decimal(price))

        with patch("apps.core.management.commands.seed_demo.timezone.localdate", return_value=delivery_date):
            call_command("seed_demo", stdout=StringIO(), stderr=StringIO())

        seeded = Delivery.objects.filter(client_reference__startswith="demo-")
        self.assertEqual(seeded.count(), 6)
        self.assertEqual(set(seeded.values_list("delivered_on", flat=True)), {delivery_date})
        self.assertEqual(set(seeded.values_list("price_schedule_id", flat=True)), {current_schedule.pk})
