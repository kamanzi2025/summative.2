"""Staging Scenario 2: stale price schedule after a mid-season update.

Spec (08-kawa-contracts-and-deltas.md): read GET /api/price-schedule/,
update the underlying schedule, re-read, and assert the new value is served
within the invalidation window documented in the student's own README.md.
Fails when a cache was added in F1 with no invalidation path -- F1 only
requires that caching exist, not that it invalidates correctly.

This project's README documents "a static in-code dict, not cached... no
cache to invalidate" -- so the invalidation window is immediate, and the
test asserts the very next read reflects the update.
"""

# Ported from the summative/seed version (eeffead) to this project's layout. Changes, and why:
# - Prices are PriceSchedule/PriceEntry rows here, not a module-level `core.views.PRICE_SCHEDULE`
#   dict, so the "update" is the real mid-season path: a new schedule for the same season, in
#   effect from today, made active with apps.pricing.services.activate_schedule(). No try/finally
#   restore is needed: the test database is rolled back after the test.
# - The response lists prices as `prices: [{"grade", "price_per_kg_rwf"}]` (decimal strings), not a
#   `prices_per_kg` dict of numbers, so a helper reads grade A from that list as a Decimal.
# - The docstring's README quote is from the reference implementation. This project's README
#   ("Cache invalidation", under "Price schedule") documents: no server-side cache, so the next
#   request serves the change; clients may reuse a response for at most
#   PRICE_SCHEDULE_MAX_AGE_SECONDS (60 s) via Cache-Control. Both halves of that window are
#   asserted: the next read is fresh, and the header allows no more than the documented 60 s.
# Scenario and the core assertion (the very next read serves the updated price) are unchanged.

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.pricing.models import PriceEntry, PriceSchedule
from apps.pricing.services import activate_schedule, get_active_schedule

DOCUMENTED_MAX_AGE_SECONDS = 60  # README.md, "Cache invalidation"


def _price_a(body):
    return next(Decimal(row["price_per_kg_rwf"]) for row in body["prices"] if row["grade"] == "A")


@pytest.mark.django_db
def test_price_schedule_reflects_update_within_documented_window(as_role):
    client = as_role("exporter_user")

    before = client.get("/api/price-schedule/")
    assert before.status_code == 200, before.content
    original_price_a = _price_a(before.json())

    updated_price_a = original_price_a + 37
    current = get_active_schedule()
    assert current is not None, "no active price schedule to update"
    mid_season = PriceSchedule.objects.create(season=current.season, effective_from=timezone.localdate())
    PriceEntry.objects.bulk_create(
        PriceEntry(
            schedule=mid_season,
            grade=entry.grade,
            price_per_kg_rwf=updated_price_a if entry.grade == "A" else entry.price_per_kg_rwf,
        )
        for entry in current.entries.all()
    )
    activate_schedule(mid_season)

    after = client.get("/api/price-schedule/")
    assert after.status_code == 200, after.content
    served_price_a = _price_a(after.json())

    assert served_price_a == updated_price_a, (
        "price-schedule endpoint served a stale value after a mid-season update -- the "
        f"README's documented invalidation window (immediate on the server) was not honoured: "
        f"expected {updated_price_a}, got {served_price_a}"
    )
    assert f"max-age={DOCUMENTED_MAX_AGE_SECONDS}" in after["Cache-Control"], (
        f"Cache-Control {after['Cache-Control']!r} lets clients keep the old price longer than the "
        f"{DOCUMENTED_MAX_AGE_SECONDS} s the README documents"
    )
