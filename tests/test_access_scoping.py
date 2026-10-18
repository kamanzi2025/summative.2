"""Enforcement of ROLE_POLICIES: who may call what (permission) and which rows they see (scope).

Runs against the real seed_rbac_fixtures data and logs in with a Django session, the way the F2
hidden checks do. Field-level rules are covered separately in field-rule tests and on the auditor
delivery detail endpoint below.
"""

from io import StringIO
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import RequestFactory
from rest_framework.test import APIClient
from rest_framework.views import APIView

from apps.accounts.permissions import RolePolicyPermission
from apps.deliveries.models import Delivery
from apps.registry.models import Farmer, Plot, WashingStation

pytestmark = pytest.mark.django_db

AGENT, EXPORTER, AUDITOR = "field_agent_user", "exporter_user", "auditor_user"
LISTS = ["/api/farmers/", "/api/plots/", "/api/deliveries/"]
SEED_PLOTS = {"KWA-SEED-K1", "KWA-SEED-K2", "KWA-SEED-M1", "KWA-SEED-M2"}


@pytest.fixture(autouse=True)
def seeded(db):
    call_command("seed_rbac_fixtures", stdout=StringIO())


def session_client(username):
    client = APIClient()
    client.force_login(User.objects.get(username=username))
    return client


@pytest.fixture
def agent():
    return session_client(AGENT)


@pytest.fixture
def grader(make_staff_user):
    make_staff_user(None, username="grader_user")
    return session_client("grader_user")


def all_rows(client, path):
    """Every row of a cursor-paginated list, following `next` to the end."""
    rows, url = [], path
    while url:
        response = client.get(url)
        assert response.status_code == 200, response.json()
        body = response.json()
        rows += body["results"]
        url = body["next"] and "{0.path}?{0.query}".format(urlsplit(body["next"]))
    return rows


def plot(code):
    return Plot.objects.get(plot_code=code)


def unattached_farmer():
    return Farmer.objects.create(full_name="Elsewhere", member_number="KWA-F-X1", phone="+250781111111")


def delivery_at(station):
    return Delivery.objects.get(washing_station__name=station, client_reference__startswith="seed-rbac-")


# --- Permission: which roles may call which endpoints ----------------------------------------


@pytest.mark.parametrize("path", [*LISTS, "/api/stations/"])
def test_authenticated_user_without_a_role_cannot_read_protected_lists(grader, path):
    assert grader.get(path).status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        lambda: f"/api/farmers/{Farmer.objects.get(member_number='KWA-F-SEED-01').pk}/",
        lambda: f"/api/plots/{plot('KWA-SEED-K1').pk}/",  # Nyaruguru
        lambda: f"/api/plots/{plot('KWA-SEED-M1').pk}/",  # Kamonyi
        lambda: f"/api/deliveries/{delivery_at('Nyaruguru').pk}/",
        lambda: f"/api/deliveries/{delivery_at('Kamonyi').pk}/",
        lambda: f"/api/stations/{WashingStation.objects.get(name='Nyaruguru').pk}/",
        lambda: f"/api/stations/{WashingStation.objects.get(name='Kamonyi').pk}/",
    ],
    ids=[
        "farmer",
        "own-plot",
        "other-station-plot",
        "own-delivery",
        "other-station-delivery",
        "own-station",
        "other-station",
    ],
)
def test_authenticated_user_without_a_role_cannot_read_own_or_other_station_details(grader, path):
    assert grader.get(path()).status_code == 403


def test_user_without_a_role_cannot_read_the_audit_log(grader):
    response = grader.get("/api/audit-log/")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/farmers/", "farmer"),
        ("/api/plots/", "own_plot"),
        ("/api/plots/", "other_station_plot"),
        ("/api/deliveries/", "own_delivery"),
        ("/api/deliveries/", "other_station_delivery"),
    ],
    ids=["farmer", "own-plot", "other-station-plot", "own-delivery", "other-station-delivery"],
)
def test_authenticated_user_without_a_role_cannot_create_records(
    grader, path, payload, farmer_payload, plot_payload, delivery_payload
):
    """F1 anonymous registrations remain public; authenticated accounts need an assigned role."""
    bodies = {
        "farmer": farmer_payload,
        "own_plot": plot_payload,
        "other_station_plot": {**plot_payload, "plot_code": "KWA-P-NO-ROLE-M1", "washing_station": "Kamonyi"},
        "own_delivery": delivery_payload,
        "other_station_delivery": {
            **delivery_payload,
            "plot": plot("KWA-SEED-M1").pk,
            "washing_station": "Kamonyi",
        },
    }
    with patch("apps.registry.tasks.run_risk_check.delay"):
        response = grader.post(path, bodies[payload], format="json")
    assert response.status_code == 403, response.content


@pytest.mark.parametrize("username", [EXPORTER, AUDITOR])
@pytest.mark.parametrize("path", LISTS)
def test_exporter_and_auditor_cannot_write(username, path):
    response = session_client(username).post(path, {}, format="json")
    assert response.status_code == 403


@pytest.mark.parametrize("username", [AGENT, EXPORTER, AUDITOR])
@pytest.mark.parametrize("path", [*LISTS, "/api/stations/"])
def test_every_role_can_read_the_lists(username, path):
    assert session_client(username).get(path).status_code == 200


def test_view_without_a_policy_resource_is_denied_to_every_role():
    class Unlabelled(APIView):
        pass

    for username in (AGENT, EXPORTER, AUDITOR):
        request = Unlabelled().initialize_request(RequestFactory().get("/"))
        request.user = User.objects.get(username=username)
        assert not RolePolicyPermission().has_permission(request, Unlabelled())


# --- Record scope: field agent sees only their station ----------------------------------------


def test_field_agent_deliveries_are_only_their_station(agent):
    rows = all_rows(agent, "/api/deliveries/")
    assert rows and {row["washing_station"] for row in rows} == {"Nyaruguru"}


def test_field_agent_plots_are_only_their_station(agent):
    rows = all_rows(agent, "/api/plots/")
    assert {row["plot_code"] for row in rows} == {"KWA-SEED-K1", "KWA-SEED-K2"}
    assert {row["washing_station"] for row in rows} == {"Nyaruguru"}


@pytest.mark.parametrize("username", [EXPORTER, AUDITOR])
def test_exporter_and_auditor_see_both_stations(username):
    client = session_client(username)
    assert {row["washing_station"] for row in all_rows(client, "/api/deliveries/")} == {"Nyaruguru", "Kamonyi"}
    assert {row["plot_code"] for row in all_rows(client, "/api/plots/")} == SEED_PLOTS


def test_field_agent_farmers_are_those_with_a_plot_or_registered_at_their_station(agent, make_farmer, make_plot):
    nyaruguru, kamonyi = WashingStation.objects.get(name="Nyaruguru"), WashingStation.objects.get(name="Kamonyi")
    registered_here = make_farmer(home_station=nyaruguru)
    # Registered at Kamonyi but delivers to Nyaruguru too: visible, because of the plot.
    plot_here = make_farmer(home_station=kamonyi)
    make_plot(farmer=plot_here, washing_station=nyaruguru)
    elsewhere = make_farmer(home_station=kamonyi)
    make_plot(farmer=elsewhere, washing_station=kamonyi)
    unattached = make_farmer()

    ids = [row["id"] for row in all_rows(agent, "/api/farmers/")]
    seed_farmer = Farmer.objects.get(member_number="KWA-F-SEED-01")  # owns K1 and K2
    assert sorted(ids) == sorted([seed_farmer.pk, registered_here.pk, plot_here.pk])
    assert elsewhere.pk not in ids and unattached.pk not in ids
    assert len(ids) == len(set(ids)), "a farmer with several plots at the station is listed once"


@pytest.mark.parametrize("username", [EXPORTER, AUDITOR])
def test_exporter_and_auditor_see_every_farmer(username, make_farmer):
    unattached = make_farmer()
    ids = {row["id"] for row in all_rows(session_client(username), "/api/farmers/")}
    assert ids == set(Farmer.objects.values_list("pk", flat=True)) and unattached.pk in ids


def test_station_list_is_scoped(agent):
    assert [row["name"] for row in agent.get("/api/stations/").json()] == ["Nyaruguru"]
    assert {row["name"] for row in session_client(AUDITOR).get("/api/stations/").json()} >= {"Nyaruguru", "Kamonyi"}


# --- Every detail route and sub-route applies the same scope ---------------------------------


@pytest.mark.parametrize(
    "path",
    [
        lambda: f"/api/plots/{plot('KWA-SEED-M1').pk}/",
        lambda: f"/api/plots/{plot('KWA-SEED-M1').pk}/risk-checks/",
        lambda: f"/api/deliveries/{delivery_at('Kamonyi').pk}/",
        lambda: f"/api/stations/{WashingStation.objects.get(name='Kamonyi').pk}/",
        lambda: f"/api/stations/{WashingStation.objects.get(name='Kamonyi').pk}/deliveries/",
        lambda: f"/api/farmers/{unattached_farmer().pk}/",
    ],
    ids=["plot", "plot-risk-checks", "delivery", "station", "station-feed", "farmer"],
)
def test_other_station_records_are_404_for_a_field_agent(agent, path):
    """404, not 403: the response must not confirm the record exists."""
    response = agent.get(path())
    assert response.status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        lambda: f"/api/plots/{plot('KWA-SEED-K1').pk}/",
        lambda: f"/api/plots/{plot('KWA-SEED-K1').pk}/risk-checks/",
        lambda: f"/api/deliveries/{delivery_at('Nyaruguru').pk}/",
        lambda: f"/api/stations/{WashingStation.objects.get(name='Nyaruguru').pk}/deliveries/",
    ],
    ids=["plot", "plot-risk-checks", "delivery", "station-feed"],
)
def test_own_station_records_are_readable_by_a_field_agent(agent, path):
    assert agent.get(path()).status_code == 200


def test_auditor_can_read_the_other_station_feed():
    kamonyi = WashingStation.objects.get(name="Kamonyi")
    rows = session_client(AUDITOR).get(f"/api/stations/{kamonyi.pk}/deliveries/").json()["results"]
    assert {row["washing_station"] for row in rows} == {"Kamonyi"}


def test_auditor_can_read_delivery_metadata_without_commercial_terms():
    delivery = delivery_at("Nyaruguru")

    response = session_client(AUDITOR).get(f"/api/deliveries/{delivery.pk}/")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["id"] == delivery.pk
    assert body["washing_station"] == "Nyaruguru"
    assert body["plot_code"] == "KWA-SEED-K1"
    assert body["weight_kg"] == str(delivery.weight_kg)
    assert body["grade"] == delivery.grade
    assert body["export_status"]
    assert "unit_price_rwf" not in body
    assert "amount_due_rwf" not in body


def test_washing_station_filter_cannot_widen_the_scope(agent):
    assert agent.get("/api/deliveries/?washing_station=Kamonyi").json()["results"] == []
    assert agent.get("/api/plots/?washing_station=Kamonyi").json()["results"] == []


# --- Writes can only point at records in scope -----------------------------------------------


def test_field_agent_cannot_register_a_plot_at_another_station(agent, plot_payload):
    plot_payload.update(washing_station="Kamonyi", plot_code="KWA-P-ELSEWHERE")
    response = agent.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 400
    assert "washing_station" in response.json()["error"]["details"]


def test_field_agent_cannot_attach_a_plot_to_another_stations_farmer(agent, plot_payload, make_farmer):
    other = make_farmer(home_station=WashingStation.objects.get(name="Kamonyi"))
    plot_payload.update(farmer=other.pk, plot_code="KWA-P-STEAL")
    response = agent.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 400
    assert "farmer" in response.json()["error"]["details"]
    assert not Plot.objects.filter(plot_code="KWA-P-STEAL").exists()


def test_field_agent_cannot_record_a_delivery_against_another_stations_plot(agent, delivery_payload):
    delivery_payload.update(plot=plot("KWA-SEED-M1").pk, washing_station="Kamonyi")
    response = agent.post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 400
    assert {"plot", "washing_station"} <= set(response.json()["error"]["details"])


def test_new_farmer_belongs_to_the_agents_station_and_stays_visible(agent, farmer_payload):
    farmer_payload.update(member_number="KWA-F-NEW", national_id="1199000000000001", phone="+250781234567")
    created = agent.post("/api/farmers/", farmer_payload, format="json")
    assert created.status_code == 201
    assert created.json()["home_station"] == "Nyaruguru"
    assert created.json()["id"] in [row["id"] for row in all_rows(agent, "/api/farmers/")]
    # A 2G resend of the same registration is still an idempotent replay, before any plot exists.
    resent = agent.post("/api/farmers/", farmer_payload, format="json")
    assert (resent.status_code, resent.json()["id"]) == (200, created.json()["id"])


def test_field_agent_cannot_register_a_farmer_at_another_station(agent, farmer_payload):
    farmer_payload.update(home_station="Kamonyi", national_id="1199000000000002", phone="+250781234568")
    response = agent.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 400
    assert "home_station" in response.json()["error"]["details"]


# --- Replays never hand back another station's record ----------------------------------------


def test_delivery_replay_of_another_stations_key_reveals_nothing(agent):
    other = delivery_at("Kamonyi")
    body = {
        "plot": other.plot_id,
        "washing_station": "Kamonyi",
        "weight_kg": str(other.weight_kg),
        "grade": other.grade,
        "delivered_on": other.delivered_on.isoformat(),
        "client_reference": other.client_reference,
    }
    response = agent.post("/api/deliveries/", body, format="json")
    assert response.status_code == 400
    assert str(other.amount_due_rwf) not in response.content.decode()
    assert Delivery.objects.filter(client_reference=other.client_reference).count() == 1


def test_plot_replay_of_another_stations_code_reveals_nothing(agent):
    m1 = plot("KWA-SEED-M1")
    body = {
        "farmer": m1.farmer_id,
        "plot_code": m1.plot_code,
        "sector": "Mbazi",
        "washing_station": "Kamonyi",
        "latitude": str(m1.latitude),
        "longitude": str(m1.longitude),
        "area_hectares": str(m1.area_hectares),
    }
    response = agent.post("/api/plots/", body, format="json")
    assert response.status_code == 400
    assert str(m1.latitude) not in response.content.decode()


def test_farmer_replay_of_an_out_of_scope_member_number_reveals_nothing(agent, make_farmer, farmer_payload):
    other = make_farmer(member_number="KWA-F-ELSEWHERE", home_station=WashingStation.objects.get(name="Kamonyi"))
    farmer_payload.update(member_number=other.member_number, full_name=other.full_name, phone=other.phone)
    farmer_payload.pop("national_id")
    farmer_payload["cooperative"] = other.cooperative
    response = agent.post("/api/farmers/", farmer_payload, format="json")
    # Not a 200 replay with the record and not a 409 carrying its id: an ordinary duplicate error.
    assert response.status_code == 400
    assert "member_number" in response.json()["error"]["details"]
    assert str(other.pk) not in str(response.json()["error"]["details"].get("id", ""))
