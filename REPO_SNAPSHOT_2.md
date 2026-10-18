<!-- REPO_SNAPSHOT part 2 of 4. Paste all parts in order. -->

# REPO SNAPSHOT (part 2 of 4, continued)

### tests/test_access_scoping.py

```python
"""Enforcement of ROLE_POLICIES: who may call what (permission) and which rows they see (scope).

Runs against the real seed_rbac_fixtures data and logs in with a Django session, the way the F2
hidden checks do. Field-level rules (masking, coarsening, commercial terms) are not enforced yet.
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
def test_user_without_a_role_can_read_the_lists(grader, path):
    assert grader.get(path).status_code == 200


def test_user_without_a_role_cannot_read_the_audit_log(grader):
    response = grader.get("/api/audit-log/")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_user_without_a_role_runs_the_f1_flow_with_the_most_restrictive_view(grader, farmer_payload):
    """The F1 contract payloads still work for a logged-in user who was never given a role, but
    every response reveals the least: no national ID, sector points, no prices."""
    farmer = grader.post("/api/farmers/", farmer_payload, format="json")
    assert farmer.status_code == 201, farmer.json()
    assert "national_id" not in farmer.json()
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
        plot = grader.post("/api/plots/", plot_body, format="json")
    assert plot.status_code == 201, plot.json()
    assert (plot.json()["latitude"], plot.json()["coordinate_precision"]) != ("-2.540000", "full")
    delivery_body = {
        "plot": plot.json()["id"],
        "washing_station": "Nyaruguru",
        "weight_kg": "38.5",
        "grade": "A",
        "delivered_on": "2026-03-14",
    }
    delivery = grader.post("/api/deliveries/", delivery_body, format="json")
    assert delivery.status_code == 201, delivery.json()
    assert "amount_due_rwf" not in delivery.json() and "unit_price_rwf" not in delivery.json()
    assert grader.post("/api/farmers/", farmer_payload, format="json").status_code == 200
    for row in grader.get("/api/farmers/").json()["results"]:
        assert "national_id" not in row
    for row in grader.get("/api/plots/").json()["results"]:
        assert row["coordinate_precision"] == "sector"


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
```

### tests/test_audit_log.py

```python
"""AuditLog: one append-only row per request to a protected endpoint, readable by auditors only."""

import json
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import RequestFactory
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.audit.models import AppendOnlyError, AuditLog
from apps.registry.models import Plot, Sector

pytestmark = pytest.mark.django_db

AGENT, EXPORTER, AUDITOR = "field_agent_user", "exporter_user", "auditor_user"


@pytest.fixture(autouse=True)
def seeded(db):
    call_command("seed_rbac_fixtures", stdout=StringIO())


def client_for(username, **kwargs):
    client = APIClient(**kwargs)
    client.force_login(User.objects.get(username=username))
    return client


def only_new_row(action):
    """Run `action` and return the single audit row it wrote."""
    before = set(AuditLog.objects.values_list("pk", flat=True))
    action()
    rows = AuditLog.objects.exclude(pk__in=before)
    assert rows.count() == 1, list(rows.values("method", "path"))
    return rows.get()


def plot_id(code):
    return Plot.objects.get(plot_code=code).pk


# --- What a row records -----------------------------------------------------------------------


def test_field_agent_list_is_recorded_with_the_rules_applied():
    row = only_new_row(lambda: client_for(AGENT).get("/api/plots/"))
    assert (row.username, row.role, row.user.username) == (AGENT, "field_agent", AGENT)
    assert (row.method, row.path, row.endpoint, row.status_code, row.resource) == (
        "GET",
        "/api/plots/",
        "plot-list",
        200,
        "plots",
    )
    assert sorted(row.object_ids) == sorted([plot_id("KWA-SEED-K1"), plot_id("KWA-SEED-K2")])
    assert (row.coordinate_precision, row.national_id, row.commercial_terms) == ("full", "last_four", True)


def test_exporter_row_records_sector_precision():
    row = only_new_row(lambda: client_for(EXPORTER).get("/api/plots/"))
    assert (row.role, row.coordinate_precision, row.national_id) == ("exporter_partner", "sector", "hidden")
    assert len(row.object_ids) == 4


def test_auditor_row_records_that_commercial_terms_were_withheld():
    row = only_new_row(lambda: client_for(AUDITOR).get("/api/deliveries/"))
    assert (row.resource, row.commercial_terms, row.coordinate_precision) == ("deliveries", False, "full")


def test_detail_and_sub_route_record_the_plot_id():
    k1 = plot_id("KWA-SEED-K1")
    client = client_for(AGENT)
    assert only_new_row(lambda: client.get(f"/api/plots/{k1}/")).object_ids == [k1]
    row = only_new_row(lambda: client.get(f"/api/plots/{k1}/risk-checks/"))
    assert (row.endpoint, row.object_ids) == ("plot-risk-checks", [k1])


def test_writes_are_recorded(plot_payload):
    plot_payload["plot_code"] = "KWA-P-AUDITED"
    with patch("apps.registry.tasks.run_risk_check.delay"):
        row = only_new_row(lambda: client_for(AGENT).post("/api/plots/", plot_payload, format="json"))
    assert (row.method, row.status_code, row.object_ids) == ("POST", 201, [plot_id("KWA-P-AUDITED")])


def test_token_requests_are_attributed_to_the_token_user():
    token, _ = Token.objects.get_or_create(user=User.objects.get(username=EXPORTER))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    row = only_new_row(lambda: client.get("/api/farmers/"))
    assert (row.username, row.role) == (EXPORTER, "exporter_partner")


# --- Refused requests are recorded too ---------------------------------------------------------


def test_anonymous_request_is_recorded():
    row = only_new_row(lambda: APIClient().get("/api/farmers/"))
    assert (row.user, row.username, row.role, row.status_code) == (None, "", "", 401)
    assert (row.coordinate_precision, row.national_id, row.commercial_terms) == ("sector", "hidden", False)


def test_anonymous_registration_is_recorded(farmer_payload):
    row = only_new_row(lambda: APIClient().post("/api/farmers/", farmer_payload, format="json"))
    assert (row.user, row.username, row.method, row.status_code, row.resource) == (None, "", "POST", 201, "farmers")
    assert len(row.object_ids) == 1


def test_user_without_a_role_is_recorded_with_the_restrictive_rules(make_staff_user):
    make_staff_user(None, username="grader_user")
    row = only_new_row(lambda: client_for("grader_user").get("/api/deliveries/"))
    assert (row.username, row.role, row.status_code) == ("grader_user", "", 200)
    assert (row.coordinate_precision, row.national_id, row.commercial_terms) == ("sector", "hidden", False)


def test_out_of_scope_attempt_is_recorded_with_the_id_asked_for():
    m1 = plot_id("KWA-SEED-M1")
    row = only_new_row(lambda: client_for(AGENT).get(f"/api/plots/{m1}/"))
    assert (row.status_code, row.object_ids) == (404, [m1])


def test_refused_write_is_recorded():
    row = only_new_row(lambda: client_for(AUDITOR).post("/api/deliveries/", {}, format="json"))
    assert (row.method, row.status_code) == ("POST", 403)


@pytest.mark.parametrize(
    "request_",
    [
        lambda c: c.get("/api/status/"),
        lambda c: c.get("/api/price-schedule/"),
        lambda c: c.post("/api/auth/api-token/", {"username": AGENT, "password": "x"}, format="json"),
    ],
    ids=["status", "price-schedule", "login"],
)
def test_public_endpoints_are_not_recorded(request_):
    before = AuditLog.objects.count()
    request_(APIClient())
    assert AuditLog.objects.count() == before


# --- Never the data itself ---------------------------------------------------------------------


def test_rows_never_contain_coordinates_or_national_ids():
    for username in (AGENT, EXPORTER, AUDITOR):
        client = client_for(username)
        client.get("/api/plots/?latitude=-2.540000&longitude=29.710000")
        client.get("/api/farmers/")
        for plot in Plot.objects.filter(plot_code__startswith="KWA-SEED-"):
            client.get(f"/api/plots/{plot.pk}/")
    stored = json.dumps(list(AuditLog.objects.values()), default=str)
    # The masked form, not a bare "6789": that could match the microseconds of a timestamp.
    secrets = {"1198770123456789", "************6789"}
    for plot in Plot.objects.all():
        secrets |= {str(plot.latitude), str(plot.longitude)}
    for sector in Sector.objects.all():
        secrets |= {str(sector.reference_latitude), str(sector.reference_longitude)}
    assert not {secret for secret in secrets if secret in stored}
    assert not AuditLog.objects.filter(path__contains="?").exists()


# --- Append-only -------------------------------------------------------------------------------


def test_rows_cannot_be_changed_or_deleted():
    row = only_new_row(lambda: client_for(AGENT).get("/api/plots/"))
    row.status_code = 200
    with pytest.raises(AppendOnlyError):
        row.save()
    with pytest.raises(AppendOnlyError):
        row.delete()
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.filter(pk=row.pk).update(username="someone-else")
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().delete()
    assert AuditLog.objects.get(pk=row.pk).username == AGENT


def test_admin_is_read_only():
    admin = site._registry[AuditLog]
    request = RequestFactory().get("/")
    request.user = User.objects.create_superuser(username="root", password="x")
    assert not admin.has_add_permission(request)
    assert not admin.has_change_permission(request)
    assert not admin.has_delete_permission(request)


def test_trail_survives_the_user_being_removed():
    row = only_new_row(lambda: client_for(EXPORTER).get("/api/plots/"))
    User.objects.filter(username=EXPORTER).delete()
    row.refresh_from_db()
    assert (row.user, row.username) == (None, EXPORTER)


def test_request_fails_if_the_trail_cannot_be_written():
    client = client_for(AGENT, raise_request_exception=False)
    with patch("apps.audit.middleware.AuditLog.objects.create", side_effect=RuntimeError("db down")):
        assert client.get("/api/plots/").status_code == 500


# --- The audit-log endpoint --------------------------------------------------------------------


def test_only_the_auditor_can_read_the_audit_log(make_staff_user):
    make_staff_user(None, username="grader_user")
    assert client_for(AUDITOR).get("/api/audit-log/").status_code == 200
    for username in (AGENT, EXPORTER, "grader_user"):
        assert client_for(username).get("/api/audit-log/").status_code == 403
    assert APIClient().get("/api/audit-log/").status_code == 401


def test_audit_log_lists_newest_first_and_records_its_own_reads():
    client_for(AGENT).get("/api/plots/")
    client = client_for(AUDITOR)
    first = client.get("/api/audit-log/").json()["results"]
    assert first[0]["username"] == AGENT and first[0]["resource"] == "plots"
    newest = client.get("/api/audit-log/").json()["results"][0]
    assert (newest["username"], newest["resource"], newest["path"]) == (AUDITOR, "audit_log", "/api/audit-log/")


def test_audit_log_filters_by_user_and_status():
    client_for(AGENT).get("/api/plots/")
    client_for(EXPORTER).post("/api/plots/", {}, format="json")
    client = client_for(AUDITOR)
    rows = client.get("/api/audit-log/", {"username": EXPORTER}).json()["results"]
    assert rows and {row["username"] for row in rows} == {EXPORTER}
    rows = client.get("/api/audit-log/", {"status_code": 403}).json()["results"]
    assert rows and {row["status_code"] for row in rows} == {403}


def test_solanges_questions_are_one_query_each():
    """The three questions in the F2 brief, answered from the audit log by URL."""
    client_for(AGENT).get("/api/plots/")
    client_for(AGENT).get("/api/farmers/")
    client_for(EXPORTER).get("/api/plots/")
    client_for(AUDITOR).get("/api/plots/")
    client = client_for(AUDITOR)

    def who(query):
        rows = client.get(f"/api/audit-log/?{query}").json()["results"]
        return {(row["username"], row["resource"]) for row in rows}

    # 1. Who has looked at exact plot coordinates?
    assert who("resource=plots&coordinate_precision=full") == {(AGENT, "plots"), (AUDITOR, "plots")}
    # 2. Who has looked at farmer identity data (the national ID) this season?
    assert who("resource=farmers&national_id=last_four&occurred_after=2026-01-01T00:00:00Z") == {(AGENT, "farmers")}
    # 3. What precision left the system for the buyer?
    rows = client.get("/api/audit-log/?role=exporter_partner&resource=plots").json()["results"]
    assert {row["coordinate_precision"] for row in rows} == {"sector"}


def test_precision_filters_reject_unknown_values():
    response = client_for(AUDITOR).get("/api/audit-log/?coordinate_precision=exact")
    assert response.status_code == 400
```

### tests/test_auth.py

```python
"""Authentication: who the caller is. Role-based authorization is tested in test_role_policies.py."""

import base64
from unittest.mock import patch

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.accounts.models import Role

pytestmark = pytest.mark.django_db

PROTECTED_LISTS = ["/api/farmers/", "/api/plots/", "/api/deliveries/"]
PROTECTED = [
    *PROTECTED_LISTS,
    "/api/stations/",
    "/api/farmers/1/",
    "/api/plots/1/",
    "/api/plots/1/risk-checks/",
    "/api/deliveries/1/",
    "/api/stations/1/deliveries/",
]
LOGIN_PATHS = ["/api/auth/staff-login/", "/api/auth/api-token/"]
STAFF_PASSWORD = "GraderPass123!"  # what make_staff_user sets


@pytest.fixture
def grader_user(make_staff_user):
    """The contract's generic credential: a valid user with no role profile."""
    return make_staff_user(None, username="grader_user")


@pytest.fixture
def agent_user(make_staff_user):
    """A user with a role, for flows that go on to call protected endpoints."""
    return make_staff_user(Role.FIELD_AGENT, username="agent")


def credentials(username):
    return {"username": username, "password": STAFF_PASSWORD}


@pytest.mark.parametrize("path", PROTECTED)
def test_anonymous_reads_are_refused(anon_api, path):
    response = anon_api.get(path)
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Token"
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize("path", PROTECTED_LISTS)
def test_anonymous_registrations_reach_validation(anon_api, path):
    """F1 had no login, so the three registrations stay open (ANONYMOUS_POLICY); reads do not."""
    response = anon_api.post(path, {}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_anonymous_f1_flow_registers_but_reveals_nothing(anon_api, farmer_payload, nyaruguru):
    farmer = anon_api.post("/api/farmers/", farmer_payload, format="json")
    assert farmer.status_code == 201, farmer.json()
    assert "national_id" not in farmer.json()
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
        plot = anon_api.post("/api/plots/", plot_body, format="json")
    assert plot.status_code == 201, plot.json()
    assert plot.json()["coordinate_precision"] == "sector"
    delivery = anon_api.post(
        "/api/deliveries/",
        {"plot": plot.json()["id"], "washing_station": "Nyaruguru", "weight_kg": "38.5", "grade": "A"},
        format="json",
    )
    assert delivery.status_code == 201, delivery.json()
    assert "amount_due_rwf" not in delivery.json()
    # Reading back is still refused.
    assert anon_api.get(f"/api/farmers/{farmer.json()['id']}/").status_code == 401
    assert anon_api.get("/api/farmers/").status_code == 401


def test_bearer_token_authenticates_like_token(agent_user):
    token, _ = Token.objects.get_or_create(user=agent_user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.key}")
    assert client.get("/api/farmers/").status_code == 200
    client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
    assert client.get("/api/farmers/").status_code == 401


def test_basic_auth_authenticates(agent_user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Basic " + base64.b64encode(b"agent:" + STAFF_PASSWORD.encode()).decode())
    assert client.get("/api/farmers/").status_code == 200
    client.credentials(HTTP_AUTHORIZATION="Basic " + base64.b64encode(b"agent:wrong").decode())
    assert client.get("/api/farmers/").status_code == 401


@pytest.mark.parametrize("path", ["/api/status/", "/api/price-schedule/"])
def test_status_and_price_schedule_stay_public(anon_api, path):
    assert anon_api.get(path).status_code == 200


@pytest.mark.parametrize("path", LOGIN_PATHS)
def test_login_returns_a_token_for_a_user_without_a_role(anon_api, grader_user, path):
    response = anon_api.post(path, credentials("grader_user"), format="json")
    assert response.status_code == 200
    assert response.json() == {"token": Token.objects.get(user=grader_user).key}


@pytest.mark.parametrize("path", LOGIN_PATHS)
def test_login_returns_the_same_token_each_time(anon_api, grader_user, path):
    body = credentials("grader_user")
    first = anon_api.post(path, body, format="json").json()["token"]
    assert anon_api.post(path, body, format="json").json()["token"] == first
    assert Token.objects.filter(user=grader_user).count() == 1


@pytest.mark.parametrize("path", LOGIN_PATHS)
@pytest.mark.parametrize(
    "body",
    [
        {"username": "grader_user", "password": "wrong"},
        {"username": "nobody", "password": STAFF_PASSWORD},
        {"username": "grader_user"},
        {},
    ],
)
def test_bad_credentials_are_rejected(anon_api, grader_user, path, body):
    response = anon_api.post(path, body, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert not Token.objects.exists()


@pytest.mark.parametrize("path", LOGIN_PATHS)
def test_inactive_user_cannot_log_in(anon_api, grader_user, path):
    grader_user.is_active = False
    grader_user.save()
    response = anon_api.post(path, credentials("grader_user"), format="json")
    assert response.status_code == 400


@pytest.mark.parametrize("path", LOGIN_PATHS)
def test_login_ignores_a_bad_authorization_header(grader_user, path):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
    response = client.post(path, credentials("grader_user"), format="json")
    assert response.status_code == 200


def test_staff_login_starts_a_session_that_authenticates_later_requests(agent_user):
    client = APIClient(enforce_csrf_checks=True)
    response = client.post("/api/auth/staff-login/", credentials("agent"), format="json")
    assert response.status_code == 200
    assert "sessionid" in response.cookies
    assert client.get("/api/farmers/").status_code == 200


def test_api_token_does_not_start_a_session(anon_api, agent_user):
    response = anon_api.post("/api/auth/api-token/", credentials("agent"), format="json")
    assert "sessionid" not in response.cookies
    assert anon_api.get("/api/farmers/").status_code == 401


def test_token_authenticates_requests(anon_api, agent_user):
    token = anon_api.post("/api/auth/api-token/", credentials("agent"), format="json").json()["token"]
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    assert client.get("/api/farmers/").status_code == 200


def test_invalid_token_is_refused():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
    assert client.get("/api/farmers/").status_code == 401


def test_session_writes_require_csrf(agent_user, farmer_payload):
    """A logged-in browser session cannot be ridden by a cross-site form post."""
    client = APIClient(enforce_csrf_checks=True)
    client.login(**credentials("agent"))
    response = client.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 403


def test_token_writes_do_not_need_csrf(agent_user, farmer_payload):
    token, _ = Token.objects.get_or_create(user=agent_user)
    client = APIClient(enforce_csrf_checks=True)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    assert client.post("/api/farmers/", farmer_payload, format="json").status_code == 201
```

### tests/test_contract.py

```python
"""Mirror of docs/autograding/F1_CONTRACT.md, using the exact payloads the hidden checks send."""

import pytest

pytestmark = pytest.mark.django_db


def test_status(anon_api):
    response = anon_api.get("/api/status/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_contract_flow_farmer_plot_delivery(agent_api):
    farmer = agent_api.post(
        "/api/farmers/",
        {
            "full_name": "Uwimana Béatrice",
            "member_number": "KWA-F-0417",
            "cooperative": "Huye",
            "national_id": "1198770123456789",
            "phone": "+250780000000",
        },
        format="json",
    )
    assert farmer.status_code == 201, farmer.json()
    assert isinstance(farmer.json()["id"], int)

    plot = agent_api.post(
        "/api/plots/",
        {
            "farmer": farmer.json()["id"],
            "plot_code": "KWA-P-0417-A",
            "sector": "Kigoma",
            "washing_station": "Nyaruguru",
            "latitude": "-2.540000",
            "longitude": "29.710000",
            "area_hectares": "0.42",
        },
        format="json",
    )
    assert plot.status_code == 201, plot.json()
    assert isinstance(plot.json()["id"], int)

    delivery = agent_api.post(
        "/api/deliveries/",
        {
            "plot": plot.json()["id"],
            "washing_station": "Nyaruguru",
            "weight_kg": "38.5",
            "grade": "A",
            "delivered_on": "2026-03-14",
        },
        format="json",
    )
    assert delivery.status_code == 201, delivery.json()
    assert isinstance(delivery.json()["id"], int)


@pytest.mark.parametrize("path", ["/api/farmers/", "/api/plots/", "/api/deliveries/"])
def test_lists_use_results_envelope(agent_api, path):
    response = agent_api.get(path)
    assert response.status_code == 200
    assert "results" in response.json()


def test_price_schedule_available_on_fresh_database(anon_api):
    assert anon_api.get("/api/price-schedule/").status_code == 200
```

### tests/test_deliveries.py

```python
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.deliveries.models import Delivery
from apps.deliveries.serializers import DeliverySerializer
from apps.pricing.models import PriceEntry, PriceSchedule
from apps.registry.models import Plot, RiskStatus

pytestmark = pytest.mark.django_db


def test_delivery_snapshots_price_and_risk_status(agent_api, delivery_payload):
    response = agent_api.post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 201
    body = response.json()
    assert body["unit_price_rwf"] == "760.00"
    assert body["amount_due_rwf"] == "29260.00"  # 38.5 kg x 760 RWF
    assert body["season"] == "2026A"
    assert body["washing_station"] == "Nyaruguru"
    assert body["plot_risk_status_at_delivery"] == "pending"
    # Accepted and paid, but not exportable until the plot is cleared.
    assert body["is_exportable"] is False


def test_later_price_change_does_not_rewrite_amount_due(agent_api, delivery_payload):
    delivery_id = agent_api.post("/api/deliveries/", delivery_payload, format="json").json()["id"]
    PriceEntry.objects.filter(grade="A").update(price_per_kg_rwf=Decimal("900.00"))
    assert agent_api.get(f"/api/deliveries/{delivery_id}/").json()["amount_due_rwf"] == "29260.00"


def test_delivery_becomes_exportable_once_plot_clears(agent_api, delivery_payload):
    delivery_id = agent_api.post("/api/deliveries/", delivery_payload, format="json").json()["id"]
    Plot.objects.filter(pk=delivery_payload["plot"]).update(risk_status=RiskStatus.CLEAR)
    body = agent_api.get(f"/api/deliveries/{delivery_id}/").json()
    assert body["is_exportable"] is True
    assert body["plot_risk_status_at_delivery"] == "pending"  # the snapshot is not rewritten


def test_flagged_plot_delivery_is_recorded_but_not_exportable(agent_api, make_plot, delivery_payload):
    delivery_payload["plot"] = make_plot(risk_status=RiskStatus.FLAGGED).pk
    body = agent_api.post("/api/deliveries/", delivery_payload, format="json").json()
    assert body["plot_risk_status_at_delivery"] == "flagged"
    assert body["is_exportable"] is False


def test_idempotent_replay_returns_original(agent_api, delivery_payload):
    delivery_payload["client_reference"] = "phone-7f3a-0001"
    first = agent_api.post("/api/deliveries/", delivery_payload, format="json")
    replay = agent_api.post("/api/deliveries/", delivery_payload, format="json")
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert Delivery.objects.count() == 1


def test_same_client_reference_at_another_station_is_a_new_delivery(
    agent_api, kamonyi_agent_api, delivery_payload, make_plot, kamonyi
):
    delivery_payload["client_reference"] = "shared-ref"
    assert agent_api.post("/api/deliveries/", delivery_payload, format="json").status_code == 201
    other = {**delivery_payload, "plot": make_plot(washing_station=kamonyi).pk, "washing_station": "Kamonyi"}
    assert kamonyi_agent_api.post("/api/deliveries/", other, format="json").status_code == 201


@pytest.mark.parametrize(
    ("weight", "message"),
    [("-5", "Must be greater than 0."), ("0", "Must be greater than 0."), ("500.01", "Must be at most 500 kg")],
)
def test_weight_out_of_range_is_rejected(agent_api, delivery_payload, weight, message):
    delivery_payload["weight_kg"] = weight
    response = agent_api.post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"]["weight_kg"][0].startswith(message)


def test_station_must_match_plot_station(delivery_payload):
    # Through the API a field agent cannot even name another station (see test_access_scoping.py),
    # so the plot/station rule is checked on the serializer alone, without a scoping request.
    delivery_payload["washing_station"] = "Kamonyi"
    serializer = DeliverySerializer(data=delivery_payload)
    assert not serializer.is_valid()
    assert "delivers to Nyaruguru" in serializer.errors["washing_station"][0]


def test_station_outside_the_agents_scope_is_rejected(agent_api, delivery_payload):
    delivery_payload["washing_station"] = "Kamonyi"
    response = agent_api.post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 400
    assert "washing_station" in response.json()["error"]["details"]


def test_future_delivery_date_is_rejected(agent_api, delivery_payload):
    delivery_payload["delivered_on"] = (timezone.localdate() + timedelta(days=1)).isoformat()
    response = agent_api.post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"]["delivered_on"] == ["Delivery date cannot be in the future."]


def test_no_active_price_is_rejected(agent_api, delivery_payload):
    PriceSchedule.objects.update(is_active=False)
    response = agent_api.post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 400
    assert "No active price for grade A" in response.json()["error"]["details"]["grade"][0]


def test_delivery_must_reference_an_existing_plot(agent_api, delivery_payload):
    delivery_payload["plot"] = 999_999
    response = agent_api.post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 400
    assert "plot" in response.json()["error"]["details"]


def test_delivered_on_defaults_to_today(agent_api, delivery_payload):
    del delivery_payload["delivered_on"]
    body = agent_api.post("/api/deliveries/", delivery_payload, format="json").json()
    assert body["delivered_on"] == timezone.localdate().isoformat()


def test_replay_with_different_body_is_a_conflict(agent_api, delivery_payload):
    delivery_payload["client_reference"] = "phone-7f3a-0002"
    original = agent_api.post("/api/deliveries/", delivery_payload, format="json").json()
    reused = {**delivery_payload, "weight_kg": "41.0", "grade": "B"}
    response = agent_api.post("/api/deliveries/", reused, format="json")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "conflict"
    assert error["details"] == {"id": original["id"], "mismatched_fields": ["weight_kg", "grade"]}
    assert Delivery.objects.count() == 1


def test_replay_matches_equivalent_decimal_forms(agent_api, delivery_payload):
    delivery_payload["client_reference"] = "phone-7f3a-0003"
    first = agent_api.post("/api/deliveries/", delivery_payload, format="json").json()
    replay = agent_api.post("/api/deliveries/", {**delivery_payload, "weight_kg": "38.50"}, format="json")
    assert replay.status_code == 200
    assert replay.json()["id"] == first["id"]
```

### tests/test_farmers.py

```python
import pytest

from apps.registry.models import Farmer

pytestmark = pytest.mark.django_db


def test_create_farmer_normalises_local_phone(agent_api, farmer_payload):
    farmer_payload["phone"] = "0780 000 000"
    response = agent_api.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 201
    assert response.json()["phone"] == "+250780000000"
    assert Farmer.objects.get().phone == "+250780000000"


def test_list_and_retrieve_farmer(agent_api, make_farmer, nyaruguru):
    farmer = make_farmer(full_name="Mukamana Claudine", home_station=nyaruguru)
    listing = agent_api.get("/api/farmers/").json()
    assert [row["id"] for row in listing["results"]] == [farmer.pk]
    assert agent_api.get(f"/api/farmers/{farmer.pk}/").json()["full_name"] == "Mukamana Claudine"


def test_national_id_is_optional(agent_api, farmer_payload):
    del farmer_payload["national_id"]
    response = agent_api.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 201
    assert response.json()["national_id"] is None


@pytest.mark.parametrize("phone", ["+254712345678", "0712345", "07812345678", "not-a-phone", "+250760000000"])
def test_rejects_non_rwandan_phone(agent_api, farmer_payload, phone):
    farmer_payload["phone"] = phone
    response = agent_api.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 400
    assert "phone" in response.json()["error"]["details"]


def test_rejects_duplicate_phone_in_other_format(agent_api, farmer_payload, make_farmer):
    make_farmer(phone="+250780000000")
    farmer_payload["phone"] = "0780000000"
    response = agent_api.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"]["phone"] == ["A farmer with this phone number already exists."]


@pytest.mark.parametrize("national_id", ["123", "11987701234567890", "1198770123456ABC"])
def test_rejects_malformed_national_id(agent_api, farmer_payload, national_id):
    farmer_payload["national_id"] = national_id
    response = agent_api.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 400
    assert "national_id" in response.json()["error"]["details"]


def test_identical_resend_replays_existing_farmer(agent_api, farmer_payload):
    first = agent_api.post("/api/farmers/", farmer_payload, format="json")
    # A 2G retry may resend the phone in local form; it normalises to the same farmer.
    replay = agent_api.post("/api/farmers/", {**farmer_payload, "phone": "0780000000"}, format="json")
    assert first.status_code == 201 and first.headers["Idempotent-Replayed"] == "false"
    assert replay.status_code == 200 and replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json()["id"] == first.json()["id"]
    assert Farmer.objects.count() == 1


def test_member_number_reused_with_different_details_is_a_conflict(agent_api, farmer_payload, make_farmer, nyaruguru):
    existing = make_farmer(member_number="KWA-F-0417", home_station=nyaruguru)
    response = agent_api.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "conflict"
    assert error["details"]["id"] == existing.pk
    assert set(error["details"]["mismatched_fields"]) == {"full_name", "phone", "national_id", "cooperative"}
```

### tests/test_feed.py

```python
"""Task 4: the cursor-paginated station delivery feed."""

from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlsplit

import pytest
from django.db import connection
from django.utils import timezone

from apps.deliveries.models import Delivery
from apps.deliveries.services import feed_queryset
from apps.pricing.models import PriceSchedule
from apps.registry.models import Farmer, Plot, RiskStatus

pytestmark = pytest.mark.django_db

BASE_TIME = timezone.now() - timedelta(days=1)


@pytest.fixture
def make_delivery(make_plot):
    schedule = PriceSchedule.objects.get(is_active=True)
    plots = {}
    counter = iter(range(1, 10_000))

    def _make(station=None, grade="A", risk=RiskStatus.CLEAR, recorded_at=None):
        n = next(counter)
        key = (station.pk if station else None, risk)
        if key not in plots:
            extra = {"washing_station": station} if station else {}
            plots[key] = make_plot(risk_status=risk, **extra)
        plot = plots[key]
        return Delivery.objects.create(
            plot=plot,
            washing_station=plot.washing_station,
            weight_kg=Decimal("30.00"),
            grade=grade,
            client_reference=f"ref-{n}",
            price_schedule=schedule,
            unit_price_rwf=Decimal("760.00"),
            amount_due_rwf=Decimal("22800.00"),
            plot_risk_status_at_delivery=plot.risk_status,
            recorded_at=recorded_at or BASE_TIME + timedelta(minutes=n),
        )

    return _make


def path_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}"


def test_page_shape_and_default_page_size(agent_api, make_delivery):
    for _ in range(25):
        make_delivery()
    body = agent_api.get("/api/deliveries/").json()
    assert set(body) == {"next", "previous", "results"}
    assert len(body["results"]) == 20
    assert "cursor=" in body["next"]
    assert body["previous"] is None
    assert set(body["results"][0]) == {
        "id",
        "client_reference",
        "washing_station",
        "plot",
        "plot_code",
        "farmer_name",
        "weight_kg",
        "grade",
        "amount_due_rwf",
        "delivered_on",
        "recorded_at",
        "is_exportable",
    }


def test_newest_first(agent_api, make_delivery):
    older, newer = make_delivery(), make_delivery()
    ids = [row["id"] for row in agent_api.get("/api/deliveries/").json()["results"]]
    assert ids == [newer.pk, older.pk]


def test_page_size_param_is_capped(agent_api, make_delivery):
    for _ in range(5):
        make_delivery()
    assert len(agent_api.get("/api/deliveries/?page_size=2").json()["results"]) == 2
    # Values above max_page_size are clamped to 100 rather than rejected.
    assert len(agent_api.get("/api/deliveries/?page_size=5000").json()["results"]) == 5


def test_cursor_is_stable_when_new_rows_arrive_between_pages(agent_api, make_delivery):
    """With offset paging, a delivery arriving mid-scroll pushes a row from page 1 onto page 2
    (a duplicate). A cursor continues from the last row actually seen."""
    original = [make_delivery().pk for _ in range(25)]
    page1 = agent_api.get("/api/deliveries/").json()

    make_delivery(recorded_at=timezone.now())  # harvest-peak arrival while the phone is paging

    page2 = agent_api.get(path_of(page1["next"])).json()
    seen = [row["id"] for row in page1["results"]] + [row["id"] for row in page2["results"]]
    assert len(seen) == len(set(seen)), "no delivery appears twice"
    assert sorted(seen) == sorted(original), "no delivery is skipped"
    assert page2["next"] is None


def test_feed_list_runs_one_query(agent_api, make_delivery, django_assert_num_queries):
    for _ in range(20):
        make_delivery()
    # One SELECT with JOINs to plot, farmer and station, regardless of page size (no N+1),
    # plus the audit-log INSERT that every protected request writes.
    with django_assert_num_queries(2) as queries:
        response = agent_api.get("/api/deliveries/?page_size=20")
    assert len(response.json()["results"]) == 20
    assert_last_query_is_audit_insert(queries)


def test_station_feed_scopes_and_counts_queries(
    agent_api, make_delivery, nyaruguru, kamonyi, django_assert_num_queries
):
    mine = [make_delivery(station=nyaruguru).pk for _ in range(3)]
    make_delivery(station=kamonyi)
    # 1 query to resolve the station (404 if unknown) + 1 for the page + 1 audit-log INSERT.
    with django_assert_num_queries(3) as queries:
        body = agent_api.get(f"/api/stations/{nyaruguru.pk}/deliveries/").json()
    assert sorted(row["id"] for row in body["results"]) == sorted(mine)
    assert_last_query_is_audit_insert(queries)


def assert_last_query_is_audit_insert(queries):
    assert queries.captured_queries[-1]["sql"].startswith('INSERT INTO "audit_auditlog"')


def test_station_feed_unknown_station_is_404(agent_api):
    response = agent_api.get("/api/stations/999999/deliveries/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_since_returns_only_newer_rows(agent_api, make_delivery):
    old = make_delivery(recorded_at=BASE_TIME)
    new = make_delivery(recorded_at=BASE_TIME + timedelta(hours=2))
    since = (BASE_TIME + timedelta(hours=1)).isoformat()
    ids = [row["id"] for row in agent_api.get("/api/deliveries/", {"since": since}).json()["results"]]
    assert ids == [new.pk]
    assert old.pk not in ids


def test_grade_and_risk_filters(agent_api, make_delivery):
    a_clear = make_delivery(grade="A", risk=RiskStatus.CLEAR)
    b_clear = make_delivery(grade="B", risk=RiskStatus.CLEAR)
    flagged = make_delivery(grade="A", risk=RiskStatus.FLAGGED)

    def ids(query: str) -> set[int]:
        return {row["id"] for row in agent_api.get(f"/api/deliveries/?{query}").json()["results"]}

    assert ids("grade=B") == {b_clear.pk}
    assert ids("risk_status=flagged") == {flagged.pk}
    assert ids("grade=A&risk_status=clear") == {a_clear.pk}


def test_exportable_filter(agent_api, make_delivery):
    clear = make_delivery(risk=RiskStatus.CLEAR)
    pending = make_delivery(risk=RiskStatus.PENDING)
    flagged = make_delivery(risk=RiskStatus.FLAGGED)

    def ids(query: str) -> set[int]:
        return {row["id"] for row in agent_api.get(f"/api/deliveries/?{query}").json()["results"]}

    assert ids("exportable=true") == {clear.pk}
    assert ids("exportable=false") == {pending.pk, flagged.pk}
    assert ids("exportable=false&risk_status=flagged") == {flagged.pk}


@pytest.mark.skipif(connection.vendor != "sqlite", reason="EXPLAIN output format is SQLite-specific")
def test_station_feed_query_uses_composite_index(nyaruguru):
    """The feed must be an index range scan, not a full scan plus sort (README: Performance)."""
    plan = feed_queryset().filter(washing_station=nyaruguru)[:21].explain()
    assert "delivery_station_feed_idx" in plan
    assert "TEMP B-TREE FOR ORDER BY" not in plan


@pytest.mark.skipif(connection.vendor != "sqlite", reason="EXPLAIN output format is SQLite-specific")
@pytest.mark.parametrize(
    ("model", "index"),
    [(Farmer, "farmer_list_cursor_idx"), (Plot, "plot_list_cursor_idx")],
)
def test_list_endpoints_page_through_an_index(db, model, index):
    """GET /api/farmers/ and /api/plots/ use the same cursor ordering; a later page must not sort."""
    cutoff = timezone.now()
    plan = model.objects.filter(created_at__lt=cutoff).order_by("-created_at", "-id")[:21].explain()
    assert index in plan
    assert "TEMP B-TREE FOR ORDER BY" not in plan
```

### tests/test_field_rules.py

```python
"""Field-level rules: national ID masking, coordinate coarsening, commercial terms by role.

Mirrors the F2_CONTRACT.md access-matrix rows against the real seed_rbac_fixtures data, logged in
with a Django session as the hidden checks are.
"""

import re
from importlib import import_module
from io import StringIO
from urllib.parse import urlsplit

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.core.management import call_command
from drf_spectacular.generators import SchemaGenerator
from rest_framework import serializers
from rest_framework.test import APIClient, APIRequestFactory

# pytest puts tests/ on sys.path (rootdir-relative "prepend" import mode).
from test_sector_reference_points import roundings

from apps.accounts.field_rules import CommercialTermField, CoordinateField, NationalIdField, PolicyFieldsMixin
from apps.deliveries.models import Delivery
from apps.registry.models import Farmer, Plot, Sector, WashingStation
from apps.registry.serializers import FarmerSerializer, PlotSerializer

pytestmark = pytest.mark.django_db

AGENT, EXPORTER, AUDITOR = "field_agent_user", "exporter_user", "auditor_user"
FULL_ID, LAST_FOUR = "1198770123456789", "6789"
STORED = {
    "KWA-SEED-K1": ("-2.540000", "29.710000"),
    "KWA-SEED-K2": ("-2.660000", "29.790000"),
    "KWA-SEED-M1": ("-2.510000", "29.520000"),
    "KWA-SEED-M2": ("-2.900000", "29.900000"),
}


@pytest.fixture(autouse=True)
def seeded(db):
    call_command("seed_rbac_fixtures", stdout=StringIO())


def client_for(username):
    client = APIClient()
    client.force_login(User.objects.get(username=username))
    return client


def all_rows(client, path):
    rows, url = [], path
    while url:
        body = client.get(url).json()
        rows += body["results"]
        url = body["next"] and "{0.path}?{0.query}".format(urlsplit(body["next"]))
    return rows


def plots_by_code(username):
    return {row["plot_code"]: row for row in all_rows(client_for(username), "/api/plots/")}


def walk(value, key=None):
    """Yield every (key, value) pair in a JSON body, at any depth."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from walk(v, k)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item, key)
    else:
        yield key, value


def national_id_traces(body):
    """Keys naming a national ID, or values carrying the full ID or any masked last-4 form."""
    for key, value in walk(body):
        if key and "national" in key:
            yield key
        if isinstance(value, str) and (FULL_ID in value or re.fullmatch(rf"\W*{LAST_FOUR}", value)):
            yield value


# --- National ID -------------------------------------------------------------------------------


def test_field_agent_sees_only_the_last_four_digits():
    body = client_for(AGENT).get("/api/farmers/").json()
    seed = next(row for row in body["results"] if row["member_number"] == "KWA-F-SEED-01")
    assert seed["national_id"] == "************6789"
    assert FULL_ID not in str(body)


def test_field_agent_detail_create_and_replay_are_masked(farmer_payload):
    client = client_for(AGENT)
    seed_id = next(r["id"] for r in client.get("/api/farmers/").json()["results"] if r["member_number"].endswith("01"))
    assert client.get(f"/api/farmers/{seed_id}/").json()["national_id"].endswith("6789")

    farmer_payload.update(member_number="KWA-F-NEW", national_id="1199000000004321", phone="+250781234567")
    created = client.post("/api/farmers/", farmer_payload, format="json")
    replayed = client.post("/api/farmers/", farmer_payload, format="json")
    for response in (created, replayed):
        assert response.json()["national_id"] == "************4321"
        assert "1199000000004321" not in response.content.decode()


@pytest.mark.parametrize("username", [EXPORTER, AUDITOR])
def test_exporter_and_auditor_get_no_national_id_field_at_all(username):
    client = client_for(username)
    rows = all_rows(client, "/api/farmers/")
    assert rows and all("national_id" not in row for row in rows)
    assert list(national_id_traces(rows)) == []
    assert list(national_id_traces(client.get(f"/api/farmers/{rows[0]['id']}/").json())) == []


@pytest.mark.parametrize("username", [AGENT, EXPORTER, AUDITOR])
@pytest.mark.parametrize("path", ["/api/plots/", "/api/deliveries/", "/api/stations/"])
def test_no_other_response_carries_a_national_id(username, path):
    assert list(national_id_traces(client_for(username).get(path).json())) == []


# --- Coordinates -------------------------------------------------------------------------------


@pytest.mark.parametrize("username", [AGENT, AUDITOR])
def test_field_agent_and_auditor_get_full_stored_precision(username):
    plots = plots_by_code(username)
    for code, row in plots.items():
        assert (row["latitude"], row["longitude"]) == STORED[code]
        assert row["coordinate_precision"] == "full"
    assert set(plots) == (set(STORED) if username == AUDITOR else {"KWA-SEED-K1", "KWA-SEED-K2"})


def test_exporter_coordinates_follow_the_contract():
    plots = plots_by_code(EXPORTER)
    point = {code: (row["latitude"], row["longitude"]) for code, row in plots.items()}
    assert point["KWA-SEED-K1"] == point["KWA-SEED-K2"]
    assert point["KWA-SEED-M1"] == point["KWA-SEED-M2"]
    assert point["KWA-SEED-K1"] != point["KWA-SEED-M1"]
    for code, (lat, lon) in point.items():
        stored_lat, stored_lon = (Plot.objects.get(plot_code=code).latitude, Plot.objects.get(plot_code=code).longitude)
        assert float(lat) not in {float(r) for r in roundings(stored_lat)}, code
        assert float(lon) not in {float(r) for r in roundings(stored_lon)}, code
        assert plots[code]["coordinate_precision"] == "sector"


def test_exporter_gets_the_sector_reference_point():
    kigoma = Sector.objects.get(name="Kigoma")
    row = plots_by_code(EXPORTER)["KWA-SEED-K1"]
    assert (row["latitude"], row["longitude"]) == (str(kigoma.reference_latitude), str(kigoma.reference_longitude))


def test_exporter_plot_detail_is_coarsened_too():
    k1 = Plot.objects.get(plot_code="KWA-SEED-K1")
    body = client_for(EXPORTER).get(f"/api/plots/{k1.pk}/").json()
    assert body["latitude"] != STORED["KWA-SEED-K1"][0]
    assert STORED["KWA-SEED-K1"][0] not in str(body) and STORED["KWA-SEED-K1"][1] not in str(body)


def test_nested_plot_copy_follows_the_same_rule():
    """The contract: a plot nested inside another response is coarsened the same way."""

    class StationWithPlots(serializers.ModelSerializer):
        plots = PlotSerializer(many=True, read_only=True)

        class Meta:
            model = WashingStation
            fields = ["name", "plots"]

    request = APIRequestFactory().get("/")
    request.user = User.objects.get(username=EXPORTER)
    nyaruguru = WashingStation.objects.get(name="Nyaruguru")
    data = StationWithPlots(nyaruguru, context={"request": request}).data
    kigoma = Sector.objects.get(name="Kigoma")
    assert {(p["latitude"], p["longitude"]) for p in data["plots"]} == {
        (str(kigoma.reference_latitude), str(kigoma.reference_longitude))
    }


def test_exporter_cannot_recover_coordinates_through_filters():
    client = client_for(EXPORTER)
    for query in ("latitude=-2.540000", "longitude=29.710000", "ordering=latitude"):
        rows = client.get(f"/api/plots/?{query}").json()["results"]
        assert all(row["coordinate_precision"] == "sector" for row in rows)


# --- Commercial terms -------------------------------------------------------------------------


def delivery_paths():
    kamonyi = WashingStation.objects.get(name="Kamonyi")
    delivery = kamonyi.deliveries.first()
    return ["/api/deliveries/", f"/api/deliveries/{delivery.pk}/", f"/api/stations/{kamonyi.pk}/deliveries/"]


def test_auditor_gets_delivery_metadata_without_commercial_terms():
    client = client_for(AUDITOR)
    for path in delivery_paths():
        body = client.get(path).json()
        for row in body.get("results", [body]):
            assert "unit_price_rwf" not in row and "amount_due_rwf" not in row
            assert {"weight_kg", "grade", "washing_station"} <= set(row)


def test_exporter_keeps_commercial_terms():
    client = client_for(EXPORTER)
    for path in delivery_paths():
        body = client.get(path).json()
        assert all("amount_due_rwf" in row for row in body.get("results", [body]))


def test_field_agent_keeps_commercial_terms(delivery_payload):
    response = client_for(AGENT).post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 201
    assert {"unit_price_rwf", "amount_due_rwf"} <= set(response.json())


# --- Fail closed and keep the published schema complete --------------------------------------


def test_serializer_without_a_request_reveals_the_least():
    farmer_data = FarmerSerializer(Farmer.objects.get(member_number="KWA-F-SEED-01")).data
    assert "national_id" not in farmer_data
    plot_data = PlotSerializer(Plot.objects.get(plot_code="KWA-SEED-K1")).data
    assert (plot_data["latitude"], plot_data["coordinate_precision"]) != (STORED["KWA-SEED-K1"][0], "full")


def test_published_schema_still_documents_every_field():
    schemas = SchemaGenerator().get_schema(request=None, public=True)["components"]["schemas"]
    assert "national_id" in schemas["Farmer"]["properties"]
    assert {"latitude", "longitude", "coordinate_precision"} <= set(schemas["Plot"]["properties"])
    assert {"unit_price_rwf", "amount_due_rwf"} <= set(schemas["Delivery"]["properties"])
    assert "amount_due_rwf" in schemas["DeliveryFeed"]["properties"]


# --- Guard: a new serializer cannot expose a protected field without its rule ------------------

PROTECTED_FIELD_CLASS = {
    "national_id": NationalIdField,
    "latitude": CoordinateField,
    "longitude": CoordinateField,
    "unit_price_rwf": CommercialTermField,
    "amount_due_rwf": CommercialTermField,
}


PROTECTED_MODELS = {
    "national_id": (Farmer,),
    "latitude": (Plot,),
    "longitude": (Plot,),
    "unit_price_rwf": (Delivery,),
    "amount_due_rwf": (Delivery,),
}


def project_serializers():
    """Every serializer class defined under apps/ (importing each app's serializers module)."""
    for config in django_apps.get_app_configs():
        if config.name.startswith("apps."):
            try:
                import_module(f"{config.name}.serializers")
            except ModuleNotFoundError:
                pass
    found, stack = set(), [serializers.Serializer]
    while stack:
        for sub in stack.pop().__subclasses__():
            stack.append(sub)
            if sub.__module__.startswith("apps."):
                found.add(sub)
    return found


def exposed_protected_fields(cls):
    """(name, field object or None) for each protected value the serializer would output.
    None means ModelSerializer would auto-generate a plain field for it."""
    declared = cls._declared_fields
    for name, field in declared.items():
        source = (field.source or name).split(".")[-1]
        if source in PROTECTED_FIELD_CLASS:
            yield source, field
    meta = getattr(cls, "Meta", None)
    model = getattr(meta, "model", None)
    if model is None:
        return
    names = getattr(meta, "fields", [])
    if names == serializers.ALL_FIELDS:
        names = [f.name for f in model._meta.get_fields()]
    for name in names:
        # Model-aware: AuditLog.national_id records *how* IDs were served, not an ID.
        if name not in declared and model in PROTECTED_MODELS.get(name, ()):
            yield name, None


def test_the_guard_finds_the_project_serializers():
    names = {cls.__name__ for cls in project_serializers()}
    assert {"FarmerSerializer", "PlotSerializer", "DeliverySerializer", "DeliveryFeedSerializer"} <= names


def test_every_serializer_exposing_a_protected_field_applies_the_policy():
    """Adding an endpoint that returns farmer, plot or delivery data needs no masking code of its
    own, but it must reuse the field classes and PolicyFieldsMixin. This fails if it does not."""
    problems = []
    for cls in project_serializers():
        for name, field in exposed_protected_fields(cls):
            expected = PROTECTED_FIELD_CLASS[name]
            if not isinstance(field, expected):
                problems.append(f"{cls.__name__}.{name} must be declared as {expected.__name__}")
            elif not issubclass(cls, PolicyFieldsMixin):
                problems.append(f"{cls.__name__} exposes {name} but does not use PolicyFieldsMixin")
    assert problems == []


def test_the_guard_catches_an_unprotected_serializer():
    class Leaky(serializers.ModelSerializer):
        class Meta:
            model = Farmer
            fields = ["id", "national_id"]

    class Forgetful(serializers.ModelSerializer):
        national_id = NationalIdField()

        class Meta:
            model = Farmer
            fields = ["id", "national_id"]

    assert list(exposed_protected_fields(Leaky)) == [("national_id", None)]
    field = dict(exposed_protected_fields(Forgetful))["national_id"]
    assert isinstance(field, NationalIdField) and not issubclass(Forgetful, PolicyFieldsMixin)


def test_a_role_that_cannot_see_the_national_id_can_still_record_it(make_staff_user, farmer_payload):
    """Hidden on output, accepted on input: registering a farmer must never drop the ID."""
    make_staff_user(None, username="no_role_user")
    client = client_for("no_role_user")
    response = client.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 201 and "national_id" not in response.json()
    assert Farmer.objects.get(pk=response.json()["id"]).national_id == farmer_payload["national_id"]
```

### tests/test_grader_smoke.py

```python
"""Run the F1 contract flow the way the Classroom 50 grader does.

The grader does not use pytest: it runs `manage.py migrate` and then drives the API with
django.test.Client inside `manage.py shell`, on a fresh database, with a `.env` copied from
`.env.example`. Outside the pytest runner Django does NOT add "testserver" to ALLOWED_HOSTS, so
a check like this is the only way to catch configuration problems the in-process tests hide.

Since F2 the protected endpoints refuse anonymous callers, so the script checks that first and
then repeats the F1 flow as a field agent logged in with a real Django session.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GRADER_SCRIPT = """
import json
from django.contrib.auth.models import User
from django.test import Client
from apps.accounts.models import Role, UserProfile
from apps.registry.models import WashingStation

anonymous = Client()
anon = {
    "lists": [anonymous.get(p).status_code for p in ("/api/farmers/", "/api/plots/", "/api/deliveries/")],
    "farmer_post": anonymous.post("/api/farmers/", data="{}", content_type="application/json").status_code,
    "status": anonymous.get("/api/status/").status_code,
    "price_schedule": anonymous.get("/api/price-schedule/").status_code,
}

agent, _ = User.objects.get_or_create(username="smoke_agent")
UserProfile.objects.get_or_create(
    user=agent,
    defaults={"role": Role.FIELD_AGENT, "washing_station": WashingStation.objects.get(name="Nyaruguru")},
)
client = Client()
client.force_login(agent)
status = client.get("/api/status/")
farmer = client.post("/api/farmers/", data=json.dumps({
    "full_name": "Uwimana Béatrice", "member_number": "KWA-F-0417", "cooperative": "Huye",
    "national_id": "1198770123456789", "phone": "+250780000000"}), content_type="application/json")
plot = client.post("/api/plots/", data=json.dumps({
    "farmer": farmer.json()["id"], "plot_code": "KWA-P-0417-A", "sector": "Kigoma",
    "washing_station": "Nyaruguru", "latitude": "-2.540000", "longitude": "29.710000",
    "area_hectares": "0.42"}), content_type="application/json")
delivery = client.post("/api/deliveries/", data=json.dumps({
    "plot": plot.json()["id"], "washing_station": "Nyaruguru", "weight_kg": "38.5", "grade": "A",
    "delivered_on": "2026-03-14"}), content_type="application/json")
print("GRADER_RESULT " + json.dumps({
    "anonymous": anon,
    "status": status.status_code,
    "farmer": [farmer.status_code, farmer.json().get("id")],
    "plot": [plot.status_code, plot.json().get("id")],
    "delivery": [delivery.status_code, delivery.json().get("id")],
    "lists": [client.get(p).status_code for p in ("/api/farmers/", "/api/plots/", "/api/deliveries/")],
    "price_schedule": client.get("/api/price-schedule/").status_code,
}))
"""


def env_from_example(database_path: Path) -> dict[str, str]:
    """Environment equivalent to `cp .env.example .env` on a clean machine."""
    env = {key: value for key, value in os.environ.items() if key not in {"DJANGO_SETTINGS_MODULE"}}
    for line in (ROOT / ".env.example").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key] = value
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    return env


def manage(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "manage.py", *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120
    )


def test_contract_flow_as_the_grader_runs_it(tmp_path):
    env = env_from_example(tmp_path / "grader.sqlite3")
    migrate = manage("migrate", "--noinput", env=env)
    assert migrate.returncode == 0, migrate.stderr

    # The grader runs several checks against ONE database, re-posting the same farmer and plot
    # (member_number KWA-F-0417, plot_code KWA-P-0417-A) each time.
    first, second = (run_grader_script(env) for _ in range(2))

    for result in (first, second):
        anon = result["anonymous"]
        assert all(code in (401, 403) for code in anon["lists"]), anon
        # F1 registrations stay open without a login (ANONYMOUS_POLICY); an empty body is a 400.
        assert anon["farmer_post"] == 400
        assert anon["status"] == 200 and anon["price_schedule"] == 200

        assert result["status"] == 200
        assert isinstance(result["farmer"][1], int)
        assert isinstance(result["plot"][1], int)
        assert result["delivery"][0] == 201 and isinstance(result["delivery"][1], int)
        assert result["lists"] == [200, 200, 200]
        assert result["price_schedule"] == 200
    assert first["farmer"][0] == 201 and first["plot"][0] == 201
    # The resend is an idempotent replay of the same records, not a duplicate-key error.
    assert second["farmer"] == [200, first["farmer"][1]]
    assert second["plot"] == [200, first["plot"][1]]


def run_grader_script(env: dict[str, str]) -> dict:
    run = manage("shell", "-c", GRADER_SCRIPT, env=env)
    assert run.returncode == 0, run.stderr[-3000:]
    line = next(line for line in run.stdout.splitlines() if line.startswith("GRADER_RESULT "))
    return json.loads(line.removeprefix("GRADER_RESULT "))
```

### tests/test_plots.py

```python
from decimal import Decimal
from unittest.mock import patch

import pytest
from kombu.exceptions import OperationalError

from apps.registry.models import Plot, RiskStatus

pytestmark = pytest.mark.django_db


def test_create_plot_returns_pending_and_enqueues_on_commit(
    agent_api, plot_payload, django_capture_on_commit_callbacks
):
    with (
        patch("apps.registry.tasks.run_risk_check.delay") as delay,
        patch("apps.registry.tasks.get_registry_client") as registry,
    ):
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            response = agent_api.post("/api/plots/", plot_payload, format="json")
        # Nothing is published until the plot row is committed.
        delay.assert_not_called()
        assert len(callbacks) == 1
        callbacks[0]()

    assert response.status_code == 201
    body = response.json()
    assert body["risk_status"] == "pending"
    assert body["sector"] == "Kigoma"
    assert body["washing_station"] == "Nyaruguru"
    delay.assert_called_once_with(body["id"])
    registry.assert_not_called()  # the registry is never called inside the request


def test_broker_outage_does_not_fail_registration(agent_api, plot_payload, django_capture_on_commit_callbacks):
    with (
        patch("apps.registry.tasks.run_risk_check.delay", side_effect=OperationalError("redis down")),
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = agent_api.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 201
    assert Plot.objects.get().risk_status == RiskStatus.PENDING


def test_list_plots_filters(auditor_api, make_plot, make_farmer, kamonyi):
    """Filters across both stations, so this reads as the auditor (who sees every station)."""
    owner = make_farmer()
    mine = make_plot(farmer=owner, risk_status=RiskStatus.CLEAR)
    make_plot(risk_status=RiskStatus.PENDING)
    other_station = make_plot(washing_station=kamonyi)

    def ids(query: str) -> list[int]:
        return [row["id"] for row in auditor_api.get(f"/api/plots/?{query}").json()["results"]]

    assert ids(f"farmer={owner.pk}") == [mine.pk]
    assert ids("risk_status=clear") == [mine.pk]
    assert ids("washing_station=Kamonyi") == [other_station.pk]
    assert len(ids("sector=kigoma")) == 3


def test_risk_check_history_endpoint(agent_api, make_plot):
    plot = make_plot()
    plot.risk_checks.create(attempt_number=1, outcome="error", error_message="503")
    plot.risk_checks.create(attempt_number=2, outcome="clear")
    history = agent_api.get(f"/api/plots/{plot.pk}/risk-checks/").json()
    assert [(a["attempt_number"], a["outcome"]) for a in history] == [(1, "error"), (2, "clear")]


def test_missing_sector_is_rejected(agent_api, plot_payload):
    del plot_payload["sector"]
    response = agent_api.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"]["sector"] == ["This field is required."]


def test_unknown_sector_is_rejected(agent_api, plot_payload):
    plot_payload["sector"] = "Atlantis"
    response = agent_api.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 400
    assert "sector" in response.json()["error"]["details"]


@pytest.mark.parametrize(
    ("field", "value"),
    # Kampala's latitude, the equator, northern Burundi, Nairobi's longitude, eastern DRC's longitude.
    [
        ("latitude", "0.347596"),
        ("latitude", "0.0"),
        ("latitude", "-2.960000"),
        ("longitude", "36.817223"),
        ("longitude", "28.0"),
    ],
)
def test_coordinates_outside_rwanda_are_rejected(agent_api, plot_payload, field, value):
    plot_payload[field] = value
    response = agent_api.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 400
    assert field in response.json()["error"]["details"]


def test_f2_fixture_plot_m2_latitude_is_accepted(agent_api, plot_payload):
    # M2 (-2.90) sits just south of the real border; the padded bounding box must still accept it.
    plot_payload.update({"plot_code": "KWA-SEED-M2", "latitude": "-2.900000", "longitude": "29.900000"})
    with patch("apps.registry.tasks.run_risk_check.delay"):
        response = agent_api.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 201, response.json()
    assert Plot.objects.get(plot_code="KWA-SEED-M2").latitude == Decimal("-2.900000")


@pytest.mark.parametrize("area", ["0", "-0.5", "51"])
def test_area_out_of_range_is_rejected(agent_api, plot_payload, area):
    plot_payload["area_hectares"] = area
    response = agent_api.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 400
    assert "area_hectares" in response.json()["error"]["details"]


def test_identical_plot_resend_replays_without_second_check(
    agent_api, plot_payload, django_capture_on_commit_callbacks
):
    with patch("apps.registry.tasks.run_risk_check.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            first = agent_api.post("/api/plots/", plot_payload, format="json")
            replay = agent_api.post("/api/plots/", {**plot_payload, "sector": "kigoma"}, format="json")
    assert first.status_code == 201
    assert replay.status_code == 200 and replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json()["id"] == first.json()["id"]
    delay.assert_called_once()  # the replay does not queue a second registry call
    assert Plot.objects.count() == 1


def test_plot_code_reused_with_different_details_is_a_conflict(agent_api, plot_payload, make_plot):
    existing = make_plot(plot_code="KWA-P-0417-A")
    response = agent_api.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"id": existing.pk, "mismatched_fields": ["farmer"]}


def test_manual_review_queue_filter(agent_api, make_plot, settings):
    from datetime import timedelta

    from django.utils import timezone

    settings.RISK_CHECK_MANUAL_REVIEW_DAYS = 7
    overdue = make_plot(risk_status=RiskStatus.UNVERIFIED, created_at=timezone.now() - timedelta(days=9))
    make_plot(risk_status=RiskStatus.UNVERIFIED)  # unverified, but still inside the window
    make_plot(risk_status=RiskStatus.CLEAR, created_at=timezone.now() - timedelta(days=9))

    queue = agent_api.get("/api/plots/?requires_manual_review=true").json()["results"]
    assert [row["id"] for row in queue] == [overdue.pk]
    assert queue[0]["requires_manual_review"] is True
    assert len(agent_api.get("/api/plots/?requires_manual_review=false").json()["results"]) == 2
```

### tests/test_pricing_and_errors.py

```python
import datetime

import pytest
from django.db import IntegrityError, transaction

from apps.pricing.models import PriceSchedule
from apps.pricing.services import activate_schedule

pytestmark = pytest.mark.django_db


def test_price_schedule_shape_and_cache_header(anon_api):
    response = anon_api.get("/api/price-schedule/")
    assert response.status_code == 200
    assert response.json() == {
        "id": PriceSchedule.objects.get(is_active=True).pk,
        "season": "2026A",
        "effective_from": "2026-03-01",
        "currency": "RWF",
        "unit": "kg",
        "prices": [
            {"grade": "A", "price_per_kg_rwf": "760.00"},
            {"grade": "B", "price_per_kg_rwf": "500.00"},
            {"grade": "C", "price_per_kg_rwf": "300.00"},
        ],
    }
    assert "max-age=60" in response.headers["Cache-Control"]


def test_price_change_is_served_on_next_request(anon_api):
    anon_api.get("/api/price-schedule/")
    PriceSchedule.objects.get(is_active=True).entries.filter(grade="A").update(price_per_kg_rwf="800.00")
    prices = anon_api.get("/api/price-schedule/").json()["prices"]
    assert prices[0] == {"grade": "A", "price_per_kg_rwf": "800.00"}


def test_no_active_schedule_is_404(anon_api):
    PriceSchedule.objects.update(is_active=False)
    response = anon_api.get("/api/price-schedule/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_only_one_active_schedule_per_season():
    with pytest.raises(IntegrityError), transaction.atomic():
        PriceSchedule.objects.create(season="2026A", effective_from=datetime.date(2026, 5, 1), is_active=True)


def test_activate_schedule_deactivates_previous():
    old = PriceSchedule.objects.get(is_active=True)
    new = PriceSchedule.objects.create(season="2026A", effective_from=datetime.date(2026, 5, 1))
    activate_schedule(new)
    old.refresh_from_db()
    assert not old.is_active and new.is_active


def test_validation_error_envelope(agent_api):
    response = agent_api.post("/api/farmers/", {}, format="json")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "The request data is invalid."
    assert error["details"]["full_name"] == ["This field is required."]


def test_not_found_envelope(agent_api):
    response = agent_api.get("/api/farmers/999999/")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "No Farmer matches the given query.", "details": {}}
    }


def test_method_not_allowed_envelope(anon_api):
    response = anon_api.delete("/api/price-schedule/")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_malformed_json_envelope(agent_api):
    response = agent_api.post("/api/farmers/", "{not json", content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "parse_error"
```

### tests/test_risk_checks.py

```python
"""Task 3: the background deforestation-risk check."""

import random
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.registry.clients import (
    RegistryTimeout,
    RegistryUnavailable,
    RiskAssessment,
    SimulatedRiskRegistry,
)
from apps.registry.models import AttemptOutcome, Plot, RiskStatus
from apps.registry.tasks import requeue_stale_risk_checks, run_risk_check

pytestmark = pytest.mark.django_db

CLEAR = RiskAssessment(status="clear", reference="SIM-1")
FLAGGED = RiskAssessment(status="flagged", reference="SIM-1")


def registry_returning(*results):
    client = MagicMock()
    client.check_plot.side_effect = list(results)
    return patch("apps.registry.tasks.get_registry_client", return_value=client), client


def outcomes(plot: Plot) -> list[str]:
    return list(plot.risk_checks.order_by("attempt_number").values_list("outcome", flat=True))


def test_success_records_attempt_and_sets_status(make_plot):
    plot = make_plot()
    patcher, _ = registry_returning(CLEAR)
    with patcher:
        result = run_risk_check.apply(args=[plot.pk])
    plot.refresh_from_db()
    assert result.get() == "clear"
    assert plot.risk_status == RiskStatus.CLEAR
    assert plot.risk_checked_at is not None
    attempt = plot.risk_checks.get()
    assert attempt.outcome == AttemptOutcome.CLEAR
    assert attempt.finished_at is not None and attempt.duration_ms is not None


def test_flagged_result(make_plot):
    plot = make_plot()
    patcher, _ = registry_returning(FLAGGED)
    with patcher:
        run_risk_check.apply(args=[plot.pk])
    plot.refresh_from_db()
    assert plot.risk_status == RiskStatus.FLAGGED


def test_failure_records_error_attempt_and_retries(make_plot):
    plot = make_plot()
    patcher, client = registry_returning(RegistryUnavailable("503"), RegistryTimeout("slow"), CLEAR)
    with patcher:
        run_risk_check.apply(args=[plot.pk])  # eager apply() runs the retries inline
    plot.refresh_from_db()
    assert client.check_plot.call_count == 3
    assert outcomes(plot) == ["error", "timeout", "clear"]
    assert plot.risk_checks.get(attempt_number=1).error_message == "503"
    assert plot.risk_status == RiskStatus.CLEAR


@pytest.mark.parametrize(("retries", "cap"), [(0, 60), (3, 480), (7, 3600)])
def test_retry_uses_capped_exponential_backoff(make_plot, retries, cap):
    plot = make_plot()
    patcher, _ = registry_returning(RegistryUnavailable("503"))
    with patcher, patch.object(run_risk_check, "retry", side_effect=RuntimeError("stop")) as retry:
        run_risk_check.apply(args=[plot.pk], retries=retries)
    kwargs = retry.call_args.kwargs
    assert isinstance(kwargs["exc"], RegistryUnavailable)
    # retry_backoff=60 with full jitter: countdown is random in [0, min(60 * 2**retries, 3600)].
    assert 0 <= kwargs["countdown"] <= cap


def test_retry_schedule_spans_hours_not_minutes():
    """Worst case across all retries must outlast a multi-hour outage (ADR-001)."""
    from celery.utils.time import get_exponential_backoff_interval

    worst = sum(
        get_exponential_backoff_interval(factor=60, retries=n, maximum=3600, full_jitter=False)
        for n in range(run_risk_check.max_retries)
    )
    assert worst == 60 + 120 + 240 + 480 + 960 + 1920 + 3600 + 3600  # 10,980 s, about 3 hours


def test_task_time_limit_is_recorded_as_timeout_and_retried(make_plot):
    plot = make_plot()
    patcher, _ = registry_returning(SoftTimeLimitExceeded(), CLEAR)
    with patcher:
        run_risk_check.apply(args=[plot.pk])
    plot.refresh_from_db()
    assert outcomes(plot) == ["timeout", "clear"]
    assert "time limit" in plot.risk_checks.get(attempt_number=1).error_message
    assert plot.risk_status == RiskStatus.CLEAR


def test_attempt_numbers_continue_after_existing_attempts(make_plot):
    plot = make_plot()
    plot.risk_checks.create(attempt_number=3, outcome="error")
    patcher, _ = registry_returning(CLEAR)
    with patcher:
        run_risk_check.apply(args=[plot.pk])
    assert list(plot.risk_checks.values_list("attempt_number", flat=True)) == [3, 4]


def test_attempt_numbers_are_unique_per_plot(make_plot):
    plot = make_plot()
    plot.risk_checks.create(attempt_number=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        plot.risk_checks.create(attempt_number=1)


def test_sweeper_closes_attempts_abandoned_by_a_dead_worker(make_plot):
    plot = make_plot(risk_status=RiskStatus.CLEAR)
    dead = plot.risk_checks.create(attempt_number=1, started_at=timezone.now() - timedelta(hours=1))
    live = plot.risk_checks.create(attempt_number=2)
    with patch("apps.registry.tasks.run_risk_check.delay"):
        requeue_stale_risk_checks.apply()
    dead.refresh_from_db()
    live.refresh_from_db()
    assert dead.outcome == AttemptOutcome.ERROR and "abandoned" in dead.error_message
    assert live.outcome == AttemptOutcome.RUNNING


def test_exhausted_retries_mark_plot_unverified(make_plot):
    plot = make_plot()
    patcher, client = registry_returning(*[RegistryUnavailable("503")] * 20)
    with patcher:
        result = run_risk_check.apply(args=[plot.pk])
    plot.refresh_from_db()
    assert plot.risk_status == RiskStatus.UNVERIFIED
    assert client.check_plot.call_count == run_risk_check.max_retries + 1
    assert set(outcomes(plot)) == {"error"}
    assert result.successful()


def test_task_is_idempotent_for_settled_plots(make_plot):
    plot = make_plot(risk_status=RiskStatus.CLEAR)
    patcher, client = registry_returning(FLAGGED)
    with patcher:
        assert run_risk_check.apply(args=[plot.pk]).get() == "clear"
    client.check_plot.assert_not_called()
    assert not plot.risk_checks.exists()


def test_missing_plot_is_ignored():
    assert run_risk_check.apply(args=[987654]).get() == "missing"


def test_sweeper_requeues_only_stale_unsettled_plots(make_plot, settings):
    settings.RISK_CHECK_STALE_HOURS = 6
    old = timezone.now() - timedelta(hours=12)
    stale_pending = make_plot(created_at=old)
    stale_unverified = make_plot(created_at=old, risk_status=RiskStatus.UNVERIFIED)
    make_plot()  # recent pending: its own retries are still running
    make_plot(created_at=old, risk_status=RiskStatus.CLEAR)
    recently_tried = make_plot(created_at=old)
    recently_tried.risk_checks.create(attempt_number=1, outcome="error")

    with patch("apps.registry.tasks.run_risk_check.delay") as delay:
        assert requeue_stale_risk_checks.apply().get() == 2
    assert {c.args[0] for c in delay.call_args_list} == {stale_pending.pk, stale_unverified.pk}


def test_unverified_plot_needs_manual_review_after_policy_window(make_plot, settings):
    settings.RISK_CHECK_MANUAL_REVIEW_DAYS = 7
    assert make_plot(
        created_at=timezone.now() - timedelta(days=8), risk_status=RiskStatus.UNVERIFIED
    ).requires_manual_review
    assert not make_plot(
        created_at=timezone.now() - timedelta(days=2), risk_status=RiskStatus.UNVERIFIED
    ).requires_manual_review
    assert not make_plot(
        created_at=timezone.now() - timedelta(days=8), risk_status=RiskStatus.CLEAR
    ).requires_manual_review


class TestSimulatedRegistry:
    def make(self, **overrides):
        options = {
            "min_latency": 0.0,
            "max_latency": 0.0,
            "failure_rate": 0.0,
            "flag_rate": 0.0,
            "timeout": 30.0,
            "rng": random.Random(7),
            "sleep": MagicMock(),
        }
        options.update(overrides)
        return SimulatedRiskRegistry(**options)

    def check(self, registry):
        return registry.check_plot(plot_code="P1", latitude=-2.54, longitude=29.71)

    def test_clear_when_healthy(self):
        assert self.check(self.make()).status == "clear"

    def test_flags(self):
        assert self.check(self.make(flag_rate=1.0)).status == "flagged"

    def test_outage(self):
        with pytest.raises(RegistryUnavailable):
            self.check(self.make(failure_rate=1.0))

    def test_timeout_when_latency_exceeds_budget(self):
        sleep = MagicMock()
        with pytest.raises(RegistryTimeout):
            self.check(self.make(min_latency=40, max_latency=40, timeout=5, sleep=sleep))
        sleep.assert_called_once_with(5)


def test_status_reports_the_risk_check_backlog(anon_api, make_plot, settings):
    """A stalled worker is visible on /api/status/ without failing the liveness probe."""
    settings.RISK_CHECK_STALE_HOURS = 6
    settings.RISK_CHECK_MANUAL_REVIEW_DAYS = 7
    make_plot()  # fresh pending: not stale yet
    make_plot(created_at=timezone.now() - timedelta(hours=7))  # stale pending
    make_plot(created_at=timezone.now() - timedelta(days=8), risk_status=RiskStatus.UNVERIFIED)
    make_plot(risk_status=RiskStatus.CLEAR)

    body = anon_api.get("/api/status/").json()

    assert body["status"] == "ok"
    backlog = body["risk_checks"]
    assert backlog["pending"] == 2
    assert backlog["unverified"] == 1
    assert backlog["stale"] == 2
    assert backlog["requires_manual_review"] == 1
    assert backlog["healthy"] is False


def test_status_is_healthy_with_no_backlog(anon_api, db):
    backlog = anon_api.get("/api/status/").json()["risk_checks"]
    assert backlog["stale"] == 0
    assert backlog["healthy"] is True
```

### tests/test_role_policies.py

```python
import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.db import IntegrityError, transaction

from apps.accounts.models import Role, UserProfile
from apps.accounts.policies import (
    ANONYMOUS_POLICY,
    NO_ROLE_POLICY,
    ROLE_POLICIES,
    Action,
    CoordinatePrecision,
    NationalIdVisibility,
    RecordScope,
    Resource,
    can,
    policy_for,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def make_staff(nyaruguru):
    def _make(role, *, station=None, username=None, **user_fields):
        user = User.objects.create_user(username=username or f"{role}_user", password="x", **user_fields)
        if role == Role.FIELD_AGENT and station is None:
            station = nyaruguru
        UserProfile.objects.create(user=user, role=role, washing_station=station)
        return User.objects.get(pk=user.pk)

    return _make


def test_every_role_has_a_policy():
    assert set(ROLE_POLICIES) == set(Role.values)


@pytest.mark.parametrize("resource", list(Resource))
def test_anonymous_callers_can_read_nothing(resource):
    assert policy_for(AnonymousUser()) is ANONYMOUS_POLICY
    assert not can(AnonymousUser(), resource, Action.READ)


def test_anonymous_callers_may_only_register_farmers_plots_and_deliveries():
    writable = {r for r in Resource if can(AnonymousUser(), r, Action.WRITE)}
    assert writable == {Resource.FARMERS, Resource.PLOTS, Resource.DELIVERIES}
    assert (ANONYMOUS_POLICY.coordinates, ANONYMOUS_POLICY.national_id, ANONYMOUS_POLICY.commercial_terms) == (
        CoordinatePrecision.SECTOR,
        NationalIdVisibility.HIDDEN,
        False,
    )


@pytest.mark.parametrize("resource", list(Resource))
@pytest.mark.parametrize("action", list(Action))
def test_no_user_at_all_is_denied_everything(resource, action):
    assert policy_for(None) is None
    assert not can(None, resource, action)


@pytest.mark.parametrize("make_user", [User.objects.create_user, User.objects.create_superuser])
def test_logged_in_user_without_a_role_gets_the_most_restrictive_f1_policy(make_user):
    user = make_user(username="no_role", password="x")
    assert policy_for(user) is NO_ROLE_POLICY
    # The F1 operations still work...
    for resource in (Resource.FARMERS, Resource.PLOTS, Resource.DELIVERIES):
        assert can(user, resource, Action.READ) and can(user, resource, Action.WRITE)
    # ...but nothing sensitive is revealed, and the audit log stays closed.
    assert not can(user, Resource.AUDIT_LOG, Action.READ)
    assert not can(user, Resource.STATIONS, Action.WRITE)
    assert (NO_ROLE_POLICY.coordinates, NO_ROLE_POLICY.national_id, NO_ROLE_POLICY.commercial_terms) == (
        CoordinatePrecision.SECTOR,
        NationalIdVisibility.HIDDEN,
        False,
    )


def test_inactive_user_without_a_role_is_still_denied():
    user = User.objects.create_user(username="gone", password="x", is_active=False)
    assert policy_for(user) is None


def test_inactive_user_is_denied_even_with_a_role(make_staff):
    user = make_staff(Role.COMPLIANCE_AUDITOR, is_active=False)
    assert policy_for(user) is None


@pytest.mark.parametrize("role", [Role.EXPORTER_PARTNER, Role.COMPLIANCE_AUDITOR])
def test_partner_and_auditor_are_read_only(make_staff, role):
    user = make_staff(role)
    for resource in Resource:
        assert not can(user, resource, Action.WRITE)
    assert can(user, Resource.PLOTS, Action.READ)


def test_field_agent_reads_and_writes_station_records_but_not_the_audit_log(make_staff):
    agent = make_staff(Role.FIELD_AGENT)
    for resource in (Resource.FARMERS, Resource.PLOTS, Resource.DELIVERIES):
        assert can(agent, resource, Action.READ)
        assert can(agent, resource, Action.WRITE)
    assert not can(agent, Resource.STATIONS, Action.WRITE)
    assert not can(agent, Resource.AUDIT_LOG, Action.READ)


def test_only_the_auditor_reads_the_audit_log(make_staff):
    assert can(make_staff(Role.COMPLIANCE_AUDITOR), Resource.AUDIT_LOG, Action.READ)
    assert not can(make_staff(Role.EXPORTER_PARTNER), Resource.AUDIT_LOG, Action.READ)


def test_policies_match_the_f2_access_matrix():
    agent, partner, auditor = (ROLE_POLICIES[r] for r in Role.values)
    assert (agent.record_scope, agent.coordinates, agent.national_id, agent.commercial_terms) == (
        RecordScope.OWN_STATION,
        CoordinatePrecision.FULL,
        NationalIdVisibility.LAST_FOUR,
        True,
    )
    assert (partner.record_scope, partner.coordinates, partner.national_id, partner.commercial_terms) == (
        RecordScope.ALL,
        CoordinatePrecision.SECTOR,
        NationalIdVisibility.HIDDEN,
        True,
    )
    # Not a ladder: the auditor sees finer coordinates than the partner but no commercial terms.
    assert (auditor.record_scope, auditor.coordinates, auditor.national_id, auditor.commercial_terms) == (
        RecordScope.ALL,
        CoordinatePrecision.FULL,
        NationalIdVisibility.HIDDEN,
        False,
    )


def test_policies_cannot_be_widened_at_runtime():
    with pytest.raises(TypeError):
        ROLE_POLICIES[Role.EXPORTER_PARTNER].grants[Resource.AUDIT_LOG] = frozenset({Action.READ})  # type: ignore[index]
    with pytest.raises(TypeError):
        ROLE_POLICIES["superuser"] = ROLE_POLICIES[Role.COMPLIANCE_AUDITOR]  # type: ignore[index]


def test_field_agent_must_have_a_station():
    user = User.objects.create_user(username="agent", password="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        UserProfile.objects.create(user=user, role=Role.FIELD_AGENT, washing_station=None)


@pytest.mark.parametrize("role", [Role.EXPORTER_PARTNER, Role.COMPLIANCE_AUDITOR])
def test_station_is_rejected_for_unscoped_roles(nyaruguru, role):
    user = User.objects.create_user(username="partner", password="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        UserProfile.objects.create(user=user, role=role, washing_station=nyaruguru)


def test_unknown_role_is_rejected_by_the_database():
    user = User.objects.create_user(username="ghost", password="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        UserProfile.objects.create(user=user, role="superuser")
```

### tests/test_sector_reference_points.py

```python
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
```

### tests/test_seed_rbac_fixtures.py

```python
"""seed_rbac_fixtures must create exactly the F2 contract fixtures, idempotently."""

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from rest_framework.test import APIClient

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
```

### tests/staging/conftest.py  (from origin/summative/seed, not on main)

```python
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def seeded_db(db):
    """Runs the F2 fixture command so field_agent_user/exporter_user/auditor_user exist."""
    call_command("seed_rbac_fixtures")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def as_role(seeded_db, api_client):
    """Returns an APIClient force-logged-in as the named seed user.

    Matches F2_CONTRACT.md: the hidden checks authenticate directly as each
    fixture user and never go through the login views.
    """

    def _as_role(username):
        user = User.objects.get(username=username)
        api_client.force_login(user)
        return api_client

    return _as_role
```

### tests/staging/test_delivery_risk_check_stranding.py  (from origin/summative/seed, not on main)

```python
"""Staging Scenario 3: deliveries stranded on a failed risk check.

Spec (08-kawa-contracts-and-deltas.md): register a plot with the external
registry forced to fail, record a delivery against it, then assert the
delivery reaches a state that can be assigned to an export lot or is
explicitly rejected with a reason. Fails when the async flow has no failure
path, leaving the delivery indefinitely in its initial state.

Written against the contract, not against this reference implementation's
current fields: as of this session, core/tasks.check_deforestation_risk is a
documented stub that never calls an external registry and always marks the
risk check "unknown" -- there is no registry-failure path yet, and Delivery
has no status field at all. This test is expected to FAIL against the
current reference (see 08-kawa-contracts-and-deltas.md's recorded staging
verification) -- that is real open Summative-stage work, not a test bug.
"""

import pytest

from core.models import Farmer

STATUS_LIKE_FIELDS = {"status", "state", "export_status", "risk_check_status", "rejection_reason"}


@pytest.mark.django_db
def test_delivery_reaches_an_observable_state_after_failed_risk_check(as_role, settings):
    # Points any real registry integration at an address that will refuse
    # the connection, forcing a failure. Inert against implementations that
    # don't yet read this setting -- see module docstring.
    settings.REGISTRY_API_URL = "http://127.0.0.1:1/unreachable-registry"

    client = as_role("field_agent_user")
    farmer = Farmer.objects.first()
    assert farmer is not None, "seed_rbac_fixtures did not create the seed farmer"

    plot_response = client.post(
        "/api/plots/",
        {
            "farmer": farmer.id,
            "plot_code": "KWA-STAGING-RISK-01",
            "sector": "Nyaruguru",
            "washing_station": "Nyaruguru",
            "latitude": "-2.550000",
            "longitude": "29.720000",
            "area_hectares": "1.00",
        },
    )
    assert plot_response.status_code == 201, plot_response.content
    plot_id = plot_response.json()["id"]

    delivery_response = client.post(
        "/api/deliveries/",
        {
            "plot": plot_id,
            "washing_station": "Nyaruguru",
            "weight_kg": "10.00",
            "grade": "A",
            "delivered_on": "2026-09-01",
        },
    )
    assert delivery_response.status_code == 201, delivery_response.content
    delivery_data = delivery_response.json()

    present = STATUS_LIKE_FIELDS & set(delivery_data.keys())
    assert present, (
        "delivery response carries no field indicating whether it can be assigned to an "
        f"export lot or was explicitly rejected (checked for {sorted(STATUS_LIKE_FIELDS)}, "
        f"got fields {sorted(delivery_data.keys())}) -- a delivery against a plot whose risk "
        "check failed is stranded with no observable state"
    )
```

### tests/staging/test_pagination_coarsening.py  (from origin/summative/seed, not on main)

```python
"""Staging Scenario 1: coordinate precision leaking under pagination.

Spec (08-kawa-contracts-and-deltas.md): authenticate as exporter_partner and
walk every page of GET /api/plots/, asserting coarsened coordinates hold on
every page -- not just the first page or the detail view. Fails when
coarsening is applied by a code path that only covers page one.
"""

from decimal import Decimal
from urllib.parse import urlsplit

import pytest

from core.models import Farmer, Plot

PAGE_SIZE = 20  # config/settings.py REST_FRAMEWORK["PAGE_SIZE"]


def _next_path(body):
    next_url = body.get("next") if isinstance(body, dict) else None
    if not next_url:
        return None
    parsed = urlsplit(next_url)
    return parsed.path + (("?" + parsed.query) if parsed.query else "")


def _results(body):
    return body["results"] if isinstance(body, dict) and "results" in body else body


@pytest.mark.django_db
def test_coarsened_coordinates_hold_on_every_page(as_role):
    client = as_role("exporter_user")
    farmer = Farmer.objects.first()
    assert farmer is not None, "seed_rbac_fixtures did not create the seed farmer"

    # The fixture command only creates 4 plots -- not enough to force a
    # second page at PAGE_SIZE=20. Add enough plots to guarantee pagination
    # actually exercises more than the first page.
    for i in range(2 * PAGE_SIZE):
        sector = "Kigoma" if i % 2 == 0 else "Mbazi"
        Plot.objects.create(
            farmer=farmer,
            plot_code=f"KWA-STAGING-{i:03d}",
            sector=sector,
            washing_station="Nyaruguru" if sector == "Kigoma" else "Kamonyi",
            latitude=Decimal("-2.000000") + Decimal(i) / Decimal(1000),
            longitude=Decimal("29.000000") + Decimal(i) / Decimal(1000),
            area_hectares=Decimal("1.00"),
        )

    seen_by_sector: dict[str, set[tuple[str, str]]] = {}
    pages_walked = 0
    path = "/api/plots/"

    while path:
        response = client.get(path)
        assert response.status_code == 200, response.content
        body = response.json()
        results = _results(body)
        assert results, f"page {pages_walked + 1} returned no results"

        for returned in results:
            raw = Plot.objects.get(plot_code=returned["plot_code"])
            returned_point = (str(returned["latitude"]), str(returned["longitude"]))
            raw_point = (str(raw.latitude), str(raw.longitude))
            assert returned_point != raw_point, (
                f"plot {returned['plot_code']} on page {pages_walked + 1} returned its raw "
                "stored coordinate to exporter_partner instead of a coarsened one"
            )
            seen_by_sector.setdefault(raw.sector, set()).add(returned_point)

        pages_walked += 1
        path = _next_path(body)

    assert pages_walked >= 2, (
        "fixture data did not force pagination -- test setup bug, not a grading signal "
        f"(only walked {pages_walked} page(s) at PAGE_SIZE={PAGE_SIZE})"
    )

    for sector, points in seen_by_sector.items():
        assert len(points) == 1, (
            f"plots in sector {sector!r} returned {len(points)} distinct coarsened points "
            "across pages instead of one consistent point per sector"
        )

    all_points = {p for points in seen_by_sector.values() for p in points}
    assert len(all_points) == len(seen_by_sector), (
        "two different sectors coarsened to the same point -- coarsening must be per-sector"
    )
```

### tests/staging/test_price_schedule_staleness.py  (from origin/summative/seed, not on main)

```python
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

import pytest

from core import views as core_views


@pytest.mark.django_db
def test_price_schedule_reflects_update_within_documented_window(as_role):
    client = as_role("exporter_user")

    before = client.get("/api/price-schedule/")
    assert before.status_code == 200, before.content
    original_price_a = before.json()["prices_per_kg"]["A"]

    updated_price_a = original_price_a + 37
    core_views.PRICE_SCHEDULE["prices_per_kg"]["A"] = updated_price_a
    try:
        after = client.get("/api/price-schedule/")
        assert after.status_code == 200, after.content
        served_price_a = after.json()["prices_per_kg"]["A"]

        assert served_price_a == updated_price_a, (
            "price-schedule endpoint served a stale value after a mid-season update -- the "
            f"README's documented invalidation window (immediate, no cache) was not honoured: "
            f"expected {updated_price_a}, got {served_price_a}"
        )
    finally:
        core_views.PRICE_SCHEDULE["prices_per_kg"]["A"] = original_price_a
```

### requirements.txt

```text
Django>=5.0,<5.2
djangorestframework>=3.15,<3.16
celery>=5.4,<5.5
redis>=5.0,<5.1
django-environ>=0.11,<0.13
django-filter>=24.3,<26
drf-spectacular>=0.28,<0.29
psycopg[binary]>=3.2,<3.3

# Test and lint tooling (kept here so `pip install -r requirements.txt && python -m pytest -q` works)
pytest>=8.3,<9
pytest-django>=4.9,<5
ruff>=0.8,<0.13
mypy>=1.13,<2
django-stubs[compatible-mypy]>=5.1,<5.2
djangorestframework-stubs>=3.15,<3.16
celery-types>=0.22,<0.27
```

### pyproject.toml

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings"
python_files = ["test_*.py"]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
line-length = 120
target-version = "py311"
extend-exclude = ["apps/*/migrations/0001_initial.py"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "DJ", "ANN", "BLE", "RUF"]
ignore = [
    "ANN401",  # Any is the honest type for DRF's untyped request.data / kwargs
    "RUF012",  # Django/DRF Meta class attributes are conventionally mutable lists
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["ANN"]
"apps/*/migrations/*" = ["ANN"]
"apps/*/admin.py" = ["RUF012"]

[tool.mypy]
python_version = "3.12"
plugins = ["mypy_django_plugin.main", "mypy_drf_plugin.main"]
check_untyped_defs = true
disallow_untyped_defs = true
warn_unused_ignores = true
exclude = ["apps/.*/migrations/", "tests/"]

[[tool.mypy.overrides]]
module = ["environ.*", "django_filters.*", "drf_spectacular.*", "kombu.*"]
ignore_missing_imports = true

[tool.django-stubs]
django_settings_module = "config.settings"
```

### Dockerfile

```dockerfile
# Development image used by docker-compose.yml (web, worker, beat).
# Production hardening (gunicorn, collectstatic, non-root user) is Summative work.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

### docker-compose.yml

```yaml
# Local infrastructure.
#   Redis only (run Django and Celery from your venv):  docker compose up -d redis
#   Everything in containers:                          docker compose --profile app up --build
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 5

  web:
    profiles: ["app"]
    build: .
    command: sh -c "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"
    env_file: .env
    environment: &container-env
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/0
      DATABASE_URL: sqlite:////app/data/db.sqlite3
    volumes:
      - db-data:/app/data
    ports:
      - "8000:8000"
    depends_on:
      redis:
        condition: service_healthy

  worker:
    profiles: ["app"]
    build: .
    command: celery -A config worker -l info
    env_file: .env
    environment: *container-env
    volumes:
      - db-data:/app/data
    depends_on:
      redis:
        condition: service_healthy

  beat:
    profiles: ["app"]
    build: .
    command: celery -A config beat -l info --schedule /tmp/celerybeat-schedule
    env_file: .env
    environment: *container-env
    volumes:
      - db-data:/app/data
    depends_on:
      redis:
        condition: service_healthy

volumes:
  db-data:
```

### .env.example

```bash
SECRET_KEY=<REDACTED>
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost,testserver
# Leave unset for SQLite; e.g. postgres://<REDACTED>@localhost:5432/kawa
# DATABASE_URL=
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
# True runs tasks inline (no worker needed). Keep False to exercise the real worker.
CELERY_TASK_ALWAYS_EAGER=False
# Empty = use the simulated registry below.
REGISTRY_API_URL=
REGISTRY_API_TIMEOUT=30
RISK_REGISTRY_MIN_LATENCY=2
RISK_REGISTRY_MAX_LATENCY=40
RISK_REGISTRY_FAILURE_RATE=0.2
RISK_REGISTRY_FLAG_RATE=0.1
RISK_CHECK_MAX_RETRIES=8
RISK_CHECK_BACKOFF_SECONDS=60
RISK_CHECK_STALE_HOURS=6
RISK_CHECK_MANUAL_REVIEW_DAYS=7
RISK_CHECK_SWEEP_MINUTES=15
PRICE_SCHEDULE_MAX_AGE_SECONDS=60
LOG_LEVEL=INFO
```

### Makefile

```
.PHONY: check lint format typecheck test schema

check: lint typecheck test schema  ## Everything CI runs

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

typecheck:
	mypy apps config manage.py

test:
	python manage.py check
	python manage.py makemigrations --check --dry-run
	python -m pytest -q

schema:
	python manage.py spectacular --file schema.yml --validate
	git diff --exit-code schema.yml
```

_No pytest.ini or setup.cfg exists; pytest is configured in pyproject.toml (above)._

### docs/autograding/F1_CONTRACT.md

````markdown
# F1 Autograding Contract

`F1` establishes the minimum API and repository contract for the first stage of the Kawa Network
case.

## Milestone tag

- `f1` -- push this tag when F1 is ready to grade: `git tag f1 && git push origin f1`

## Required root artifacts

- `ADR.md`
- `README.md`
- either `schema.yml` or `schema.yaml`

## Required endpoints

Your project must expose these paths exactly:

- `GET /api/status/`
- `POST /api/farmers/`
- `GET /api/farmers/`
- `POST /api/plots/`
- `GET /api/plots/`
- `POST /api/deliveries/`
- `GET /api/deliveries/`
- `GET /api/price-schedule/`

`GET /api/price-schedule/` is required even though caching it is optional. You choose either
pagination or caching as your assessed performance feature in Task 4, but the endpoint itself must
exist either way, because Formative 2 and the Summative both depend on it.

`GET /api/plots/` is required because Formative 2's access matrix governs plot coordinates on it.
If your design stores location only on the farmer, add a plot resource now — Formative 2 assumes
one exists.

`GET /api/farmers/` is required for the same reason: Formative 2's access matrix governs national
ID masking on it. Without a farmer list, that part of the matrix has nothing to check.

## Status response

`GET /api/status/` must return `200`. Any JSON body is acceptable as long as it is valid JSON.

## Farmer list contract

`GET /api/farmers/` must:

- return `200`
- return valid JSON
- show a pagination-minded list structure (a DRF-style envelope containing `results`, or a
  top-level JSON list)

## Farmer create contract

The hidden tests submit:

```json
{
  "full_name": "Uwimana Béatrice",
  "member_number": "KWA-F-0417",
  "cooperative": "Huye",
  "national_id": "1198770123456789",
  "phone": "+250780000000"
}
```

`POST /api/farmers/` must:

- return `201`
- return JSON containing an integer-like `id`

## Plot create contract

The hidden tests submit:

```json
{
  "farmer": 1,
  "plot_code": "KWA-P-0417-A",
  "sector": "Kigoma",
  "washing_station": "Nyaruguru",
  "latitude": "-2.540000",
  "longitude": "29.710000",
  "area_hectares": "0.42"
}
```

`POST /api/plots/` must:

- return `201`
- return JSON containing an integer-like `id`

Two fields matter beyond the create response. `sector` carries the administrative unit that
Formative 2's coordinate coarsening is keyed to. `washing_station` says which station the plot
delivers to, and Formative 2's access scoping depends on it. You may name either field
differently in your own model, provided `docs/RBAC_MATRIX.md` documents the mapping in Formative
2 — but both concepts must exist by the end of F1.

## Plot list contract

`GET /api/plots/` must:

- return `200`
- return valid JSON
- show a pagination-minded list structure (a DRF-style envelope containing `results`, or a
  top-level JSON list)

## Delivery create contract

The hidden tests submit:

```json
{
  "plot": 1,
  "washing_station": "Nyaruguru",
  "weight_kg": "38.5",
  "grade": "A",
  "delivered_on": "2026-03-14"
}
```

`POST /api/deliveries/` must:

- return `201`
- return JSON containing an integer-like `id`

A delivery must reference a plot, not a farmer directly. The provenance chain from an export lot
back to the land the coffee grew on depends on this.

## Delivery list contract

`GET /api/deliveries/` must:

- return `200`
- return valid JSON
- show a pagination-minded list structure

Accepted list structures:

- a DRF-style pagination envelope containing `results`
- a top-level JSON list

If you use a top-level list, your README must explicitly explain the pagination or performance
decision you chose instead.

## Price schedule contract

`GET /api/price-schedule/` must:

- return `200`
- return valid JSON

Whether the response is cached is your decision. If you cache it, your README must describe how
the cache is invalidated when the season's prices change.

## Async evidence contract

The hidden checks expect evidence that asynchronous work was designed intentionally, for the
deforestation-risk check queued when a plot is registered.

At least one of the following must be visible in the codebase:

- a Python file containing `shared_task`
- a Python file containing `.delay(`
- a Python file containing `.apply_async(`
- a project-level `celery.py`

Your README must also describe how the async worker is started in your implementation.

## Performance evidence contract

The hidden checks expect evidence of at least one performance-minded design choice.

Accepted evidence includes any of:

- paginated list responses
- explicit cache configuration or cache usage
- documented query optimization in code comments or README

The hidden checks only score the objective evidence. Your rationale belongs in `ADR.md`.
````

### docs/autograding/F2_CONTRACT.md

````markdown
# F2 Autograding Contract

`F2` retrofits the `F1` codebase with authentication, authorization, and compliance-minded
controls for the Kawa Network case.

## Milestone tag

- `f2` -- push this tag when F2 is ready to grade: `git tag f2 && git push origin f2`. Your work
  continues on the same repository and the same history as F1; there is no separate branch to
  create.

## Required root artifacts

- `DECISION_LOG.md`
- `docs/RBAC_MATRIX.md`

`docs/RBAC_MATRIX.md` documents your role model in prose, for a human grader. The automated
matrix checks do not parse it — they call the management command below.

## Required fixture command

Your project must provide a Django management command:

```bash
python manage.py seed_rbac_fixtures
```

Idempotent: running it twice must not error or duplicate data. It must create, using your own
models directly (not the HTTP API), exactly:

**Three users**, each already configured with the correct role in your system, however your
implementation represents that:

| Username | Password | Role | Notes |
|---|---|---|---|
| `field_agent_user` | `GraderPass123!` | `field_agent` | scoped to washing station `Nyaruguru` |
| `exporter_user` | `GraderPass123!` | `exporter_partner` | not scoped to a station |
| `auditor_user` | `GraderPass123!` | `compliance_auditor` | not scoped to a station |

**One farmer**, so the national-ID masking checks have a real value to mask:

- `full_name`: `Uwimana Béatrice`, `national_id`: `1198770123456789` (last four: `6789`),
  `member_number`: `KWA-F-SEED-01`

**Four plots**, matching the fixture table below exactly, all owned by the seed farmer.

**Two deliveries**: one against plot `KWA-SEED-K1` (`washing_station` `Nyaruguru`), one against
plot `KWA-SEED-M1` (`washing_station` `Kamonyi`), any valid weight, grade, and date. The hidden
checks read each delivery's `washing_station` field, not its plot, to check scoping — make sure
your delivery serializer includes it.

The hidden checks fetch `field_agent_user`, `exporter_user`, and `auditor_user` from your database
by username and authenticate as each directly. They never call your login views to test the
matrix — the staff-login and token endpoints below are tested separately, on their own, with a
generic credential that carries no role.

## Required authentication endpoints

Your project must expose these paths exactly:

- `POST /api/auth/staff-login/`
- `POST /api/auth/api-token/`

The hidden checks submit:

```json
{
  "username": "grader_user",
  "password": "GraderPass123!"
}
```

Accepted token response shapes:

- a JSON object containing `token`
- a JSON object containing `access`

## Protected API expectation

None of the three `F1` list endpoints may remain open to anonymous access.

`GET /api/deliveries/`, `GET /api/plots/`, and `GET /api/farmers/` must each return `401` or `403`
for an unauthenticated requester.

## Authentication class requirement

Your `DEFAULT_AUTHENTICATION_CLASSES` must include
`rest_framework.authentication.SessionAuthentication`, in addition to whatever token or JWT
authentication you build for API consumers. The hidden checks authenticate as a logged-in Django
session user to drive the access-matrix assertions below — a token-only configuration will return
`401`/`403` to every one of them and score zero on this section, regardless of whether your RBAC
logic is otherwise correct.

This does not stop you from also requiring a token for real API consumers such as the registry
integration; the two authentication classes coexist.

## Access matrix

Your implementation must enforce this table:

| Role | `GET /api/deliveries/` | `GET /api/plots/` | Farmer national ID | Audit log |
|---|---|---|---|---|
| `field_agent` | own washing station only | own station's plots, full coordinates | masked, last 4 digits | no access |
| `exporter_partner` | all stations | all plots, coarsened coordinates | not present | no access |
| `compliance_auditor` | metadata only, no commercial terms | all plots, full coordinates | not present | read |
| unauthenticated | `401` or `403` | `401` or `403` | n/a | n/a |

Read the `exporter_partner` and `compliance_auditor` rows together. The auditor receives *more*
precise location data than the commercial partner and *less* commercial data. Neither role is
simply "more access" than the other — this cannot be implemented as a permission ladder.

Wherever a plot appears nested inside another response (for example, inside a delivery), the same
rule applies to the nested copy.

### The four fixture plots

The hidden checks create these four plots exactly, two in sector `Kigoma` and two in `Mbazi`:

| Plot | `plot_code` | Sector | Washing station | Latitude | Longitude |
|---|---|---|---|---|---|
| K1 | `KWA-SEED-K1` | Kigoma | `Nyaruguru` | `-2.540000` | `29.710000` |
| K2 | `KWA-SEED-K2` | Kigoma | `Nyaruguru` | `-2.660000` | `29.790000` |
| M1 | `KWA-SEED-M1` | Mbazi | `Kamonyi` | `-2.510000` | `29.520000` |
| M2 | `KWA-SEED-M2` | Mbazi | `Kamonyi` | `-2.900000` | `29.900000` |

`field_agent_user` is scoped to `Nyaruguru`, so K1 and K2 are the agent's own plots and M1 and M2
belong to a different station. The `plot_code` values are exact and the hidden checks match plots
by them in your `GET /api/plots/` response — your plot create/list must echo `plot_code` back.

### Access matrix checks

| Role fixture | Request | Expected |
|---|---|---|
| `field_agent` at station A | `GET /api/deliveries/` | `200`, and no delivery whose `washing_station` is station B appears on any page |
| `field_agent` at station A | `GET /api/plots/` | `200`, and no plot whose `washing_station` is station B appears |
| `field_agent` | any plot response | coordinates at full stored precision |
| `field_agent` | any farmer response | national ID appears only as the last 4 digits, never in full |
| `exporter_partner` | `GET /api/deliveries/` | `200`, deliveries from both stations appear |
| `exporter_partner` | `GET /api/plots/` | K1 and K2 return **identical** coordinates to each other |
| `exporter_partner` | `GET /api/plots/` | M1 and M2 return **identical** coordinates to each other |
| `exporter_partner` | `GET /api/plots/` | the K1/K2 coordinate differs from the M1/M2 coordinate |
| `exporter_partner` | `GET /api/plots/` | no returned coordinate equals the plot's stored coordinate rounded to any precision from 0 to 6 decimal places |
| `exporter_partner` | any farmer or plot response | no national ID field appears at all |
| `compliance_auditor` | `GET /api/plots/` | `200`, all four plots, coordinates at full stored precision |
| `compliance_auditor` | any response | no national ID field appears at all |
| `field_agent` | `GET /api/farmers/` | `200`, the seed farmer's national ID appears with only its last 4 digits (`6789`) visible; the full 16-digit value never appears anywhere in the response |
| `exporter_partner` | `GET /api/farmers/` | `200`, the full national ID never appears; no field carrying even the last-4 masked form appears either |
| `compliance_auditor` | `GET /api/farmers/` | `200`, the full national ID never appears; no field carrying even the last-4 masked form appears either |
| unauthenticated | any of the three list endpoints | `401` or `403` |

### What "coarsened" means

Rounding decimal degrees will not satisfy the coarsening checks, and this is deliberate. The
fixture coordinates are chosen so that no rounding precision from 0 to 6 decimal places passes
every assertion above: at 0 decimal places all four plots collapse to the same value, and at 1 or
more decimal places the two plots within each sector separate from each other. Coarsening has to
be keyed to the administrative unit (`sector`), not to numeric precision.

If your sector reference point legitimately coincides with a rounding of one stored coordinate,
document it in `docs/RBAC_MATRIX.md` and raise it with your facilitator before submission.

## Continuity expectation

The retrofit must preserve the original project rather than restarting from scratch.

The hidden checks look for:

- a working `manage.py`
- the original `F1` API paths still present
- existing repository continuity: the same repository, same commit history, extended rather than replaced

## Privacy or auditability expectation

The hidden checks require at least one objective signal that privacy or auditability was added.

Accepted evidence includes:

- a Python file containing `audit`
- a Python file containing `AuditLog`
- a Python file containing `created_by`
- a Python file containing `updated_by`
- a Python file containing `request.user`

The hidden checks only confirm objective evidence exists. Your reasoning belongs in
`DECISION_LOG.md`.
````

### docs/autograding/SUMMATIVE_CONTRACT.md  (not requested; included because it defines the staging scenarios)

````markdown
# Summative Autograding Contract

The Summative stage hardens the existing Kawa Network codebase for rollout readiness.

## Milestone tag

- `summative` -- push this tag when the Summative is ready to grade:
  `git tag summative && git push origin summative`.

## Required root artifacts

- `BUG_REPORT.md`
- `Dockerfile`
- `DEPLOYMENT.md`

## Required command behavior

The repository must support:

```bash
pip install -r requirements.txt
python manage.py migrate --noinput
python -m pytest -q
```

## Staging scenarios

At the start of Week 7 you merge `summative/seed`, which adds `tests/staging/`. It contains three
scenario tests driving your API the way the pilot at Nyaruguru drove it. Each probes a fault that
Formative 1 or Formative 2 permits but does not require you to close:

1. **Coordinate precision under pagination** — walks every page of `GET /api/plots/` as
   `exporter_partner` and asserts coarsened coordinates hold on every page, not just the first.
2. **Stale price schedule** — reads `GET /api/price-schedule/`, updates the underlying schedule,
   and asserts the new value is served within the invalidation window your own README documents.
3. **Delivery stranded on a failed risk check** — registers a plot with the external registry
   forced to fail, records a delivery against it, and asserts the delivery reaches a state that
   can be assigned to an export lot, or is explicitly rejected with a reason.

Run the staging tests yourself before submitting. Whichever fail are yours to diagnose in
`BUG_REPORT.md`, with a failing test written before the fix. If all three pass, that is a real
result: `BUG_REPORT.md` must then explain which decision in F1 or F2 prevented each scenario, and
you must find and document at least one defect of your own.

## Regression expectation

The hidden checks rerun key `F1` and `F2` objective checks, including every access-matrix and
coarsening assertion. The Summative must not break previously working core behavior unless the
release notes justify a change and preserve equivalent functionality.

## Student test suite expectation

`python -m pytest -q` must execute successfully.

This requirement is about your own maintained test suite, not the hidden tests.

## Deployment and readiness evidence

The hidden checks expect:

- a `Dockerfile`
- a `DEPLOYMENT.md` with explicit run or release guidance
- environment handling documented in the repository

The hidden checks may also look for readiness signals such as:

- `gunicorn`
- `uvicorn`
- `collectstatic`
- `ALLOWED_HOSTS`
- `DEBUG`

The deployment reasoning itself is graded manually.
````

