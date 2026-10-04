"""Sector reference points: the location exporters receive instead of a plot's own coordinates.

F2_CONTRACT.md requires that coarsening is keyed to the sector, not to numeric precision: plots in
one sector share a point, the two fixture sectors differ, and no served point equals any rounding
(0-6 decimal places) of a stored fixture coordinate.
"""

from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.management.commands.seed_rbac_fixtures import PLOTS
from apps.registry.models import Sector

pytestmark = pytest.mark.django_db

FIXTURE_COORDINATES = {Decimal(value) for *_, lat, lon in PLOTS for value in (lat, lon)}


def roundings(value: Decimal) -> set[Decimal]:
    """Every way a checker might round `value` to 0-6 decimal places."""
    results = set()
    for places in range(7):
        exponent = Decimal(1).scaleb(-places)
        results.add(value.quantize(exponent, rounding=ROUND_HALF_UP))
        results.add(value.quantize(exponent, rounding=ROUND_HALF_EVEN))
        results.add(Decimal(str(round(float(value), places))))
    return results


FORBIDDEN = set().union(*(roundings(value) for value in FIXTURE_COORDINATES))


def test_every_sector_has_a_reference_point():
    assert Sector.objects.exists()
    assert not Sector.objects.filter(centroid_latitude__isnull=True).exists()
    assert not Sector.objects.filter(centroid_longitude__isnull=True).exists()


@pytest.mark.parametrize("sector", ["Kigoma", "Mbazi"])
def test_fixture_sector_points_are_not_a_rounding_of_any_fixture_coordinate(sector):
    for component in Sector.objects.get(name=sector).reference_point:
        assert component not in FORBIDDEN, f"{sector} {component} equals a rounded fixture coordinate"


def test_no_sector_point_is_a_rounding_of_any_fixture_coordinate():
    for sector in Sector.objects.all():
        assert not set(sector.reference_point) & FORBIDDEN, sector.name


def test_the_two_fixture_sectors_have_different_points():
    kigoma, mbazi = (Sector.objects.get(name=name).reference_point for name in ("Kigoma", "Mbazi"))
    assert kigoma[0] != mbazi[0] and kigoma[1] != mbazi[1]


def test_rounding_cannot_satisfy_the_contract_but_the_sector_points_do():
    """Sanity check of the contract's premise, so the test above is checking the right thing."""
    by_sector: dict[str, list[tuple[Decimal, Decimal]]] = {}
    for _, sector, _, lat, lon in PLOTS:
        by_sector.setdefault(sector, []).append((Decimal(lat), Decimal(lon)))
    for places in range(7):
        exponent = Decimal(1).scaleb(-places)
        rounded = {s: {(a.quantize(exponent), b.quantize(exponent)) for a, b in pts} for s, pts in by_sector.items()}
        same_within = all(len(points) == 1 for points in rounded.values())
        differ_between = rounded["Kigoma"] != rounded["Mbazi"]
        assert not (same_within and differ_between), f"rounding to {places} places would pass"


def test_reference_point_must_be_inside_rwanda():
    sector = Sector.objects.get(name="Kigoma")
    sector.centroid_latitude = Decimal("0.3476")  # Kampala
    with pytest.raises(IntegrityError), transaction.atomic():
        sector.save()


def test_reference_point_is_required():
    with pytest.raises(IntegrityError), transaction.atomic():
        Sector.objects.create(name="Nowhere", district="Huye", centroid_latitude=Decimal("-2.6"))
