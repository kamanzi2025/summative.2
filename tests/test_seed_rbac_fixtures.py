"""seed_rbac_fixtures must create exactly the F2 contract fixtures, idempotently."""

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command

from apps.accounts.models import Role, UserProfile
from apps.deliveries.models import Delivery
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


def test_reuses_the_farmer_registered_by_the_f1_flow(farmer_payload, make_farmer):
    """The F1 contract flow registers the same national ID under KWA-F-0417."""
    f1_farmer = make_farmer(**{k: v for k, v in farmer_payload.items() if k != "cooperative"})
    seed()
    assert Farmer.objects.filter(national_id=NATIONAL_ID).count() == 1
    farmer = Farmer.objects.get(pk=f1_farmer.pk)
    assert (farmer.member_number, farmer.phone) == ("KWA-F-SEED-01", "+250788999001")


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


def test_refuses_when_national_id_and_member_number_are_different_farmers(make_farmer):
    make_farmer(national_id=NATIONAL_ID)
    make_farmer(member_number="KWA-F-SEED-01")
    with pytest.raises(CommandError, match="Resolve this by hand"):
        seed()
    assert not User.objects.exists(), "the whole run is rolled back"


def test_refuses_when_the_seed_phone_belongs_to_someone_else(make_farmer):
    make_farmer(phone="+250788999001")
    with pytest.raises(CommandError, match="Seed phone"):
        seed()
    assert not Plot.objects.exists()


def test_seeded_users_can_obtain_a_token(anon_api):
    seed()
    for username in ("field_agent_user", "exporter_user", "auditor_user"):
        response = anon_api.post("/api/auth/api-token/", {"username": username, "password": PASSWORD}, format="json")
        assert response.status_code == 200 and response.json()["token"]
