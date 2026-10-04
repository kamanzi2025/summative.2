from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Role, UserProfile
from apps.registry.models import Farmer, Plot, RiskStatus, Sector, WashingStation

STAFF_PASSWORD = "GraderPass123!"


@pytest.fixture(autouse=True)
def _fast_registry(settings: Any) -> None:
    """Never sleep for real in tests, and never run Celery tasks inline by accident."""
    settings.RISK_REGISTRY_MIN_LATENCY = 0
    settings.RISK_REGISTRY_MAX_LATENCY = 0
    settings.CELERY_TASK_ALWAYS_EAGER = False
    # Every API test creates a staff user; real PBKDF2 hashing would dominate the suite's runtime.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def anon_api() -> APIClient:
    """No credentials: only /api/status/, /api/price-schedule/ and the auth endpoints answer."""
    return APIClient()


@pytest.fixture
def make_staff_user(db: None) -> Callable[..., User]:
    """A user with a role profile; field agents default to the Nyaruguru station."""

    def _make(role: str | None, *, station: WashingStation | None = None, username: str | None = None) -> User:
        user = User.objects.create_user(username=username or f"{role or 'no_role'}_user", password=STAFF_PASSWORD)
        if role is not None:
            if role == Role.FIELD_AGENT and station is None:
                station = WashingStation.objects.get(name="Nyaruguru")
            UserProfile.objects.create(user=user, role=role, washing_station=station)
        return User.objects.select_related("profile__washing_station").get(pk=user.pk)

    return _make


def _client_for(user: User) -> APIClient:
    # force_authenticate skips the session/token lookup, so query-count tests measure the view
    # alone. tests/test_auth.py drives real session and token authentication end to end.
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def agent_api(make_staff_user: Callable[..., User]) -> APIClient:
    return _client_for(make_staff_user(Role.FIELD_AGENT))


@pytest.fixture
def exporter_api(make_staff_user: Callable[..., User]) -> APIClient:
    return _client_for(make_staff_user(Role.EXPORTER_PARTNER))


@pytest.fixture
def auditor_api(make_staff_user: Callable[..., User]) -> APIClient:
    return _client_for(make_staff_user(Role.COMPLIANCE_AUDITOR))


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
