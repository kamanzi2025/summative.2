from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.registry.models import Farmer, Plot, RiskStatus, Sector, WashingStation


@pytest.fixture(autouse=True)
def _fast_registry(settings: Any) -> None:
    """Never sleep for real in tests, and never run Celery tasks inline by accident."""
    settings.RISK_REGISTRY_MIN_LATENCY = 0
    settings.RISK_REGISTRY_MAX_LATENCY = 0
    settings.CELERY_TASK_ALWAYS_EAGER = False


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def nyaruguru(db: None) -> WashingStation:
    return WashingStation.objects.get(name="Nyaruguru")


@pytest.fixture
def kamonyi(db: None) -> WashingStation:
    return WashingStation.objects.get(name="Kamonyi")


@pytest.fixture
def kigoma(db: None) -> Sector:
    return Sector.objects.get(name="Kigoma")


@pytest.fixture
def make_farmer(db: None) -> Callable[..., Farmer]:
    counter = iter(range(1, 10_000))

    def _make(**overrides: Any) -> Farmer:
        n = next(counter)
        fields = {
            "full_name": f"Farmer {n}",
            "member_number": f"KWA-F-T{n:04d}",
            "phone": f"+25078{n:07d}",
        }
        fields.update(overrides)
        return Farmer.objects.create(**fields)

    return _make


@pytest.fixture
def make_plot(
    db: None, make_farmer: Callable[..., Farmer], kigoma: Sector, nyaruguru: WashingStation
) -> Callable[..., Plot]:
    counter = iter(range(1, 10_000))

    def _make(**overrides: Any) -> Plot:
        n = next(counter)
        fields: dict[str, Any] = {
            "farmer": overrides.pop("farmer", None) or make_farmer(),
            "plot_code": f"KWA-P-T{n:04d}",
            "sector": kigoma,
            "washing_station": nyaruguru,
            "latitude": Decimal("-2.540000"),
            "longitude": Decimal("29.710000"),
            "area_hectares": Decimal("0.42"),
            "risk_status": RiskStatus.PENDING,
        }
        fields.update(overrides)
        return Plot.objects.create(**fields)

    return _make


@pytest.fixture
def farmer_payload() -> dict[str, Any]:
    return {
        "full_name": "Uwimana Béatrice",
        "member_number": "KWA-F-0417",
        "cooperative": "Huye",
        "national_id": "1198770123456789",
        "phone": "+250780000000",
    }


@pytest.fixture
def plot_payload(make_farmer: Callable[..., Farmer]) -> dict[str, Any]:
    return {
        "farmer": make_farmer().pk,
        "plot_code": "KWA-P-0417-A",
        "sector": "Kigoma",
        "washing_station": "Nyaruguru",
        "latitude": "-2.540000",
        "longitude": "29.710000",
        "area_hectares": "0.42",
    }


@pytest.fixture
def delivery_payload(make_plot: Callable[..., Plot]) -> dict[str, Any]:
    return {
        "plot": make_plot().pk,
        "washing_station": "Nyaruguru",
        "weight_kg": "38.5",
        "grade": "A",
        "delivered_on": "2026-03-14",
    }
