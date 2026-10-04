"""Sector reference points: the location exporters receive instead of a plot's own coordinates.

F2_CONTRACT.md requires that coarsening is keyed to the sector, not to numeric precision: plots in
one sector share a point, the two fixture sectors differ, and no served point is a rounding
(0-6 decimal places) of a stored fixture coordinate. These tests apply the strictest reading of
that rule: rounding *both* values to the same precision must never make them agree, on either axis.
"""

from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.management.commands.seed_rbac_fixtures import PLOTS
from apps.registry.models import Sector

pytestmark = pytest.mark.django_db

PRECISIONS = range(7)
FIXTURE_LATITUDES = {Decimal(lat) for *_, lat, _ in PLOTS}
FIXTURE_LONGITUDES = {Decimal(lon) for *_, lon in PLOTS}


def roundings(value: Decimal) -> set[Decimal]:
    """Every way a checker might round `value` to 0-6 decimal places."""
    results = set()
    for places in PRECISIONS:
        results |= rounded(value, places)
    return results


def rounded(value: Decimal, places: int) -> set[Decimal]:
    """`value` rounded to `places`, by every common method (half-up, half-even, float round)."""
    exponent = Decimal(1).scaleb(-places)
    return {
        value.quantize(exponent, rounding=ROUND_HALF_UP),
        value.quantize(exponent, rounding=ROUND_HALF_EVEN),
        Decimal(str(round(float(value), places))),
    }


def agrees_when_both_rounded(point: Decimal, stored: Decimal) -> int | None:
    """The first precision at which rounding both values makes them equal, or None."""
    for places in PRECISIONS:
        if rounded(point, places) & rounded(stored, places):
            return places
    return None


def test_every_sector_has_a_reference_point():
    assert Sector.objects.exists()
    assert not Sector.objects.filter(reference_latitude__isnull=True).exists()
    assert not Sector.objects.filter(reference_longitude__isnull=True).exists()


@pytest.mark.parametrize("sector", ["Kigoma", "Mbazi"])
def test_fixture_sector_points_are_not_a_rounding_of_any_fixture_coordinate(sector):
    lat, lon = Sector.objects.get(name=sector).reference_point
    forbidden = set().union(*(roundings(v) for v in FIXTURE_LATITUDES | FIXTURE_LONGITUDES))
    assert lat not in forbidden and lon not in forbidden


@pytest.mark.parametrize("sector", ["Kigoma", "Mbazi", "Kibeho", "Ngera", "Ruheru", "Runda"])
def test_no_reference_point_agrees_with_a_fixture_coordinate_at_any_precision(sector):
    """Stricter than the contract's wording: round the served point *and* the stored coordinate
    to the same precision (0-6 places, any rounding method); they must still differ, on each axis."""
    lat, lon = Sector.objects.get(name=sector).reference_point
    for stored in FIXTURE_LATITUDES:
        assert agrees_when_both_rounded(lat, stored) is None, (sector, "lat", stored)
    for stored in FIXTURE_LONGITUDES:
        assert agrees_when_both_rounded(lon, stored) is None, (sector, "lon", stored)


def test_reference_points_are_distinct_per_sector():
    points = list(Sector.objects.values_list("reference_latitude", "reference_longitude"))
    assert len(points) == len(set(points))
    kigoma, mbazi = (Sector.objects.get(name=name).reference_point for name in ("Kigoma", "Mbazi"))
    assert kigoma[0] != mbazi[0] and kigoma[1] != mbazi[1]


def test_rounding_cannot_satisfy_the_contract_but_the_sector_points_do():
    """Sanity check of the contract's premise, so the tests above are checking the right thing."""
    by_sector: dict[str, list[tuple[Decimal, Decimal]]] = {}
    for _, sector, _, lat, lon in PLOTS:
        by_sector.setdefault(sector, []).append((Decimal(lat), Decimal(lon)))
    for places in PRECISIONS:
        exponent = Decimal(1).scaleb(-places)
        rounded_points = {
            s: {(a.quantize(exponent), b.quantize(exponent)) for a, b in pts} for s, pts in by_sector.items()
        }
        same_within = all(len(points) == 1 for points in rounded_points.values())
        differ_between = rounded_points["Kigoma"] != rounded_points["Mbazi"]
        assert not (same_within and differ_between), f"rounding to {places} places would pass"


def test_reference_point_must_be_inside_rwanda():
    sector = Sector.objects.get(name="Kigoma")
    sector.reference_latitude = Decimal("0.3476")  # Kampala
    with pytest.raises(IntegrityError), transaction.atomic():
        sector.save()


def test_reference_point_is_required():
    with pytest.raises(IntegrityError), transaction.atomic():
        Sector.objects.create(name="Nowhere", district="Huye", reference_latitude=Decimal("-2.6"))
