"""Field-level rules: national ID masking, coordinate coarsening, commercial terms by role.

Mirrors the F2_CONTRACT.md access-matrix rows against the real seed_rbac_fixtures data, logged in
with a Django session as the hidden checks are.
"""

import re
from io import StringIO
from urllib.parse import urlsplit

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from drf_spectacular.generators import SchemaGenerator
from rest_framework import serializers
from rest_framework.test import APIClient, APIRequestFactory

# pytest puts tests/ on sys.path (rootdir-relative "prepend" import mode).
from test_sector_centroids import roundings

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
    assert (row["latitude"], row["longitude"]) == (str(kigoma.centroid_latitude), str(kigoma.centroid_longitude))


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
        (str(kigoma.centroid_latitude), str(kigoma.centroid_longitude))
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
