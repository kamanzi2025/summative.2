from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.deliveries.models import Delivery
from apps.pricing.models import PriceEntry, PriceSchedule
from apps.registry.models import Plot, RiskStatus

pytestmark = pytest.mark.django_db


def test_delivery_snapshots_price_and_risk_status(api, delivery_payload):
    response = api.post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 201
    body = response.json()
    assert body["unit_price_rwf"] == "760.00"
    assert body["amount_due_rwf"] == "29260.00"  # 38.5 kg x 760 RWF
    assert body["season"] == "2026A"
    assert body["washing_station"] == "Nyaruguru"
    assert body["plot_risk_status_at_delivery"] == "pending"
    # Accepted and paid, but not exportable until the plot is cleared.
    assert body["is_exportable"] is False


def test_later_price_change_does_not_rewrite_amount_due(api, delivery_payload):
    delivery_id = api.post("/api/deliveries/", delivery_payload, format="json").json()["id"]
    PriceEntry.objects.filter(grade="A").update(price_per_kg_rwf=Decimal("900.00"))
    assert api.get(f"/api/deliveries/{delivery_id}/").json()["amount_due_rwf"] == "29260.00"


def test_delivery_becomes_exportable_once_plot_clears(api, delivery_payload):
    delivery_id = api.post("/api/deliveries/", delivery_payload, format="json").json()["id"]
    Plot.objects.filter(pk=delivery_payload["plot"]).update(risk_status=RiskStatus.CLEAR)
    body = api.get(f"/api/deliveries/{delivery_id}/").json()
    assert body["is_exportable"] is True
    assert body["plot_risk_status_at_delivery"] == "pending"  # the snapshot is not rewritten


def test_flagged_plot_delivery_is_recorded_but_not_exportable(api, make_plot, delivery_payload):
    delivery_payload["plot"] = make_plot(risk_status=RiskStatus.FLAGGED).pk
    body = api.post("/api/deliveries/", delivery_payload, format="json").json()
    assert body["plot_risk_status_at_delivery"] == "flagged"
    assert body["is_exportable"] is False


def test_idempotent_replay_returns_original(api, delivery_payload):
    delivery_payload["client_reference"] = "phone-7f3a-0001"
    first = api.post("/api/deliveries/", delivery_payload, format="json")
    replay = api.post("/api/deliveries/", delivery_payload, format="json")
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert Delivery.objects.count() == 1


def test_same_client_reference_at_another_station_is_a_new_delivery(api, delivery_payload, make_plot, kamonyi):
    delivery_payload["client_reference"] = "shared-ref"
    assert api.post("/api/deliveries/", delivery_payload, format="json").status_code == 201
    other = {**delivery_payload, "plot": make_plot(washing_station=kamonyi).pk, "washing_station": "Kamonyi"}
    assert api.post("/api/deliveries/", other, format="json").status_code == 201


@pytest.mark.parametrize(
    ("weight", "message"),
    [("-5", "Must be greater than 0."), ("0", "Must be greater than 0."), ("500.01", "Must be at most 500 kg")],
)
def test_weight_out_of_range_is_rejected(api, delivery_payload, weight, message):
    delivery_payload["weight_kg"] = weight
    response = api.post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"]["weight_kg"][0].startswith(message)


def test_station_must_match_plot_station(api, delivery_payload):
    delivery_payload["washing_station"] = "Kamonyi"
    response = api.post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 400
    assert "delivers to Nyaruguru" in response.json()["error"]["details"]["washing_station"][0]


def test_future_delivery_date_is_rejected(api, delivery_payload):
    delivery_payload["delivered_on"] = (timezone.localdate() + timedelta(days=1)).isoformat()
    response = api.post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"]["delivered_on"] == ["Delivery date cannot be in the future."]


def test_no_active_price_is_rejected(api, delivery_payload):
    PriceSchedule.objects.update(is_active=False)
    response = api.post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 400
    assert "No active price for grade A" in response.json()["error"]["details"]["grade"][0]


def test_delivery_must_reference_an_existing_plot(api, delivery_payload):
    delivery_payload["plot"] = 999_999
    response = api.post("/api/deliveries/", delivery_payload, format="json")
    assert response.status_code == 400
    assert "plot" in response.json()["error"]["details"]


def test_delivered_on_defaults_to_today(api, delivery_payload):
    del delivery_payload["delivered_on"]
    body = api.post("/api/deliveries/", delivery_payload, format="json").json()
    assert body["delivered_on"] == timezone.localdate().isoformat()
