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
