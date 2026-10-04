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
