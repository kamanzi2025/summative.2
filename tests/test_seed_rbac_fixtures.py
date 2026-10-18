"""seed_rbac_fixtures must create exactly the F2 contract fixtures, idempotently."""

import datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from rest_framework.test import APIClient

from apps.accounts.management.commands.seed_rbac_fixtures import DELIVERED_ON
from apps.accounts.models import Role, UserProfile
from apps.deliveries.models import Delivery
from apps.pricing.models import PriceEntry, PriceSchedule
from apps.pricing.services import activate_schedule
from apps.registry.models import Farmer, Plot

pytestmark = pytest.mark.django_db

PASSWORD = "GraderPass123!"
NATIONAL_ID = "1198770123456789"
EXPECTED_PLOTS = {
    "KWA-SEED-K1": ("Kigoma", "Nyaruguru", "-2.540000", "29.710000"),
    "KWA-SEED-K2": ("Kigoma", "Nyaruguru", "-2.660000", "29.790000"),
    "KWA-SEED-M1": ("Mbazi", "Kamonyi", "-2.510000", "29.520000"),
    "KWA-SEED-M2": ("Mbazi", "Kamonyi", "-2.900000", "29.900000"),
}


def seed():
    call_command("seed_rbac_fixtures", stdout=StringIO())


def snapshot():
    return {
        "users": sorted(User.objects.values_list("pk", "username")),
        "profiles": sorted(UserProfile.objects.values_list("pk", "user__username", "role", "washing_station__name")),
        "farmers": sorted(Farmer.objects.values_list("pk", "member_number", "national_id", "phone")),
        "plots": sorted(Plot.objects.values_list("pk", "plot_code", "farmer_id")),
        "deliveries": sorted(Delivery.objects.values_list("pk", "client_reference", "amount_due_rwf")),
    }


def test_creates_the_three_role_users():
    seed()
    expected = {
        "field_agent_user": (Role.FIELD_AGENT, "Nyaruguru"),
        "exporter_user": (Role.EXPORTER_PARTNER, None),
        "auditor_user": (Role.COMPLIANCE_AUDITOR, None),
    }
    for username, (role, station) in expected.items():
        user = User.objects.select_related("profile__washing_station").get(username=username)
        assert user.check_password(PASSWORD)
        assert user.is_active
        assert user.profile.role == role
        assert (user.profile.washing_station.name if user.profile.washing_station else None) == station


def test_creates_the_seed_farmer():
    seed()
    farmer = Farmer.objects.get(member_number="KWA-F-SEED-01")
    assert farmer.full_name == "Uwimana Béatrice"
    assert farmer.national_id == NATIONAL_ID
    assert farmer.national_id[-4:] == "6789"


def test_creates_the_four_fixture_plots_owned_by_the_seed_farmer():
    seed()
    farmer = Farmer.objects.get(member_number="KWA-F-SEED-01")
    plots = Plot.objects.select_related("sector", "washing_station").filter(plot_code__startswith="KWA-SEED-")
    assert {
        p.plot_code: (p.sector.name, p.washing_station.name, str(p.latitude), str(p.longitude)) for p in plots
    } == EXPECTED_PLOTS
    assert {p.farmer_id for p in plots} == {farmer.pk}


def test_creates_one_delivery_per_station():
    seed()
    deliveries = Delivery.objects.select_related("plot", "washing_station").order_by("client_reference")
    assert [(d.client_reference, d.plot.plot_code, d.washing_station.name) for d in deliveries] == [
        ("seed-rbac-K1", "KWA-SEED-K1", "Nyaruguru"),
        ("seed-rbac-M1", "KWA-SEED-M1", "Kamonyi"),
    ]
    for delivery in deliveries:
        assert delivery.amount_due_rwf == delivery.weight_kg * delivery.unit_price_rwf


def test_seeded_deliveries_use_price_effective_on_the_fixture_delivery_date():
    original = PriceSchedule.objects.get(is_active=True)
    later_effective_date = DELIVERED_ON + datetime.timedelta(days=1)
    later = PriceSchedule.objects.create(season=original.season, effective_from=later_effective_date)
    PriceEntry.objects.bulk_create(
        PriceEntry(
            schedule=later,
            grade=entry.grade,
            price_per_kg_rwf=Decimal("900.00") if entry.grade == "A" else entry.price_per_kg_rwf,
        )
        for entry in original.entries.all()
    )
    activate_schedule(later)

    # At seed time, the newer schedule has taken effect; the fixture delivery itself is backdated.
    with patch(
        "apps.pricing.services.timezone.localdate",
        return_value=later_effective_date + datetime.timedelta(days=1),
    ):
        seed()

    delivery = Delivery.objects.get(client_reference="seed-rbac-K1")
    assert delivery.delivered_on == DELIVERED_ON
    assert delivery.price_schedule_id == original.pk
    assert delivery.unit_price_rwf == original.entries.get(grade="A").price_per_kg_rwf


def test_running_twice_creates_no_duplicates():
    seed()
    first = snapshot()
    seed()
    assert snapshot() == first
    assert len(first["users"]) == 3 and len(first["farmers"]) == 1
    assert len(first["plots"]) == 4 and len(first["deliveries"]) == 2


def test_queues_no_risk_check(django_capture_on_commit_callbacks):
    with patch("apps.registry.tasks.run_risk_check.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            seed()
    assert callbacks == []
    delay.assert_not_called()


def test_leaves_the_f1_flows_farmer_alone(farmer_payload, make_farmer):
    """The F1 contract flow registers the same person and national ID under KWA-F-0417. The seed
    farmer is a separate membership (KWA-F-SEED-01), so the F1 record is not touched."""
    f1_farmer = make_farmer(**{k: v for k, v in farmer_payload.items() if k != "cooperative"})
    seed()
    seed()
    assert Farmer.objects.filter(national_id=NATIONAL_ID).count() == 2
    f1_farmer.refresh_from_db()
    assert (f1_farmer.member_number, f1_farmer.phone) == ("KWA-F-0417", "+250780000000")


def test_f1_contract_flow_still_works_after_seeding(farmer_payload):
    """The F1 farmer, plot and delivery payloads, posted by the field agent after seeding."""
    seed()
    client = APIClient()
    client.force_login(User.objects.get(username="field_agent_user"))
    farmer = client.post("/api/farmers/", farmer_payload, format="json")
    assert farmer.status_code == 201, farmer.json()
    plot_body = {
        "farmer": farmer.json()["id"],
        "plot_code": "KWA-P-0417-A",
        "sector": "Kigoma",
        "washing_station": "Nyaruguru",
        "latitude": "-2.540000",
        "longitude": "29.710000",
        "area_hectares": "0.42",
    }
    with patch("apps.registry.tasks.run_risk_check.delay"):
        plot = client.post("/api/plots/", plot_body, format="json")
    assert plot.status_code == 201, plot.json()
    delivery_body = {
        "plot": plot.json()["id"],
        "washing_station": "Nyaruguru",
        "weight_kg": "38.5",
        "grade": "A",
        "delivered_on": "2026-03-14",
    }
    delivery = client.post("/api/deliveries/", delivery_body, format="json")
    assert delivery.status_code == 201, delivery.json()
    # And an identical resend is still an idempotent replay.
    assert client.post("/api/farmers/", farmer_payload, format="json").status_code == 200


def test_resets_a_farmer_found_by_member_number(make_farmer):
    existing = make_farmer(member_number="KWA-F-SEED-01", full_name="Wrong Name", national_id="1199999999999999")
    seed()
    farmer = Farmer.objects.get(pk=existing.pk)
    assert (farmer.full_name, farmer.national_id) == ("Uwimana Béatrice", NATIONAL_ID)


def test_resets_a_changed_password_role_and_station(kamonyi):
    seed()
    user = User.objects.get(username="field_agent_user")
    user.set_password("something-else")
    user.is_active = False
    user.save()
    UserProfile.objects.filter(user=user).update(washing_station=kamonyi)
    seed()
    user.refresh_from_db()
    assert user.check_password(PASSWORD) and user.is_active
    assert user.profile.washing_station.name == "Nyaruguru"


def test_moves_a_plot_code_taken_by_another_farmer_onto_the_seed_farmer(make_plot):
    stray = make_plot(plot_code="KWA-SEED-M2", latitude=Decimal("-2.500000"))
    seed()
    stray.refresh_from_db()
    assert stray.farmer.member_number == "KWA-F-SEED-01"
    assert stray.latitude == Decimal("-2.900000")


def test_refuses_when_the_seed_phone_belongs_to_someone_else(make_farmer):
    make_farmer(phone="+250788999001")
    with pytest.raises(CommandError, match="Seed phone"):
        seed()
    assert not Plot.objects.exists() and not User.objects.exists(), "the whole run is rolled back"


def test_seeded_users_can_obtain_a_token(anon_api):
    seed()
    for username in ("field_agent_user", "exporter_user", "auditor_user"):
        response = anon_api.post("/api/auth/api-token/", {"username": username, "password": PASSWORD}, format="json")
        assert response.status_code == 200 and response.json()["token"]
