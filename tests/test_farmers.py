import pytest

from apps.registry.models import Farmer

pytestmark = pytest.mark.django_db


def test_create_farmer_normalises_local_phone(api, farmer_payload):
    farmer_payload["phone"] = "0780 000 000"
    response = api.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 201
    assert response.json()["phone"] == "+250780000000"
    assert Farmer.objects.get().phone == "+250780000000"


def test_list_and_retrieve_farmer(api, make_farmer):
    farmer = make_farmer(full_name="Mukamana Claudine")
    listing = api.get("/api/farmers/").json()
    assert [row["id"] for row in listing["results"]] == [farmer.pk]
    assert api.get(f"/api/farmers/{farmer.pk}/").json()["full_name"] == "Mukamana Claudine"


def test_national_id_is_optional(api, farmer_payload):
    del farmer_payload["national_id"]
    response = api.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 201
    assert response.json()["national_id"] is None


@pytest.mark.parametrize("phone", ["+254712345678", "0712345", "07812345678", "not-a-phone", "+250760000000"])
def test_rejects_non_rwandan_phone(api, farmer_payload, phone):
    farmer_payload["phone"] = phone
    response = api.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 400
    assert "phone" in response.json()["error"]["details"]


def test_rejects_duplicate_phone_in_other_format(api, farmer_payload, make_farmer):
    make_farmer(phone="+250780000000")
    farmer_payload["phone"] = "0780000000"
    response = api.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"]["phone"] == ["A farmer with this phone number already exists."]


@pytest.mark.parametrize("national_id", ["123", "11987701234567890", "1198770123456ABC"])
def test_rejects_malformed_national_id(api, farmer_payload, national_id):
    farmer_payload["national_id"] = national_id
    response = api.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 400
    assert "national_id" in response.json()["error"]["details"]


def test_rejects_duplicate_member_number(api, farmer_payload, make_farmer):
    make_farmer(member_number="KWA-F-0417")
    response = api.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 400
    assert "member_number" in response.json()["error"]["details"]
