from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.deliveries.models import Delivery
from apps.deliveries.serializers import DeliverySerializer
from apps.pricing.models import PriceEntry, PriceSchedule
from apps.pricing.services import activate_schedule
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
    # Accepted with an amount-due snapshot, but not exportable until the plot is cleared.
    assert body["is_exportable"] is False


def test_later_price_change_does_not_rewrite_amount_due(agent_api, delivery_payload):
    delivery_id = agent_api.post("/api/deliveries/", delivery_payload, format="json").json()["id"]
    PriceEntry.objects.filter(grade="A").update(price_per_kg_rwf=Decimal("900.00"))
    assert agent_api.get(f"/api/deliveries/{delivery_id}/").json()["amount_due_rwf"] == "29260.00"


def test_late_synced_delivery_uses_price_effective_on_delivery_date(agent_api, delivery_payload):
    current = PriceSchedule.objects.get(is_active=True)
    old_price = current.entries.get(grade="A").price_per_kg_rwf
    effective_on = timezone.localdate() - timedelta(days=1)
    future_price = PriceSchedule.objects.create(
        season="2026B",
        effective_from=effective_on,
    )
    PriceEntry.objects.bulk_create(
        PriceEntry(
            schedule=future_price,
            grade=entry.grade,
            price_per_kg_rwf=Decimal("900.00") if entry.grade == "A" else entry.price_per_kg_rwf,
        )
        for entry in current.entries.all()
    )
    activate_schedule(future_price)

    # A late sync for a delivery before the new effective date keeps the old rate.
    delivery_payload["delivered_on"] = (effective_on - timedelta(days=1)).isoformat()
    before = agent_api.post("/api/deliveries/", delivery_payload, format="json")
    assert before.status_code == 201, before.content
    assert before.json()["unit_price_rwf"] == str(old_price)

    # The same date boundary selects the globally effective schedule, whatever its season label.
    delivery_payload["delivered_on"] = effective_on.isoformat()
    on_effective_date = agent_api.post("/api/deliveries/", delivery_payload, format="json")
    assert on_effective_date.status_code == 201, on_effective_date.content
    assert on_effective_date.json()["unit_price_rwf"] == "900.00"

    # A delivery processed after the update also uses the new rate for its delivery date.
    delivery_payload["delivered_on"] = timezone.localdate().isoformat()
    after = agent_api.post("/api/deliveries/", delivery_payload, format="json")
    assert after.status_code == 201, after.content
    assert after.json()["unit_price_rwf"] == "900.00"


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


@pytest.mark.parametrize(
    ("risk_status", "expected_status", "reason_fragment"),
    [
        (RiskStatus.CLEAR, "eligible", "clear"),
        (RiskStatus.PENDING, "held", "pending"),
        (RiskStatus.FLAGGED, "rejected", "flagged"),
        (RiskStatus.UNVERIFIED, "held", "unverified"),
    ],
)
def test_export_status_explains_current_plot_risk_status(
    agent_api, make_plot, delivery_payload, risk_status, expected_status, reason_fragment
):
    delivery_payload["plot"] = make_plot(risk_status=risk_status).pk
    body = agent_api.post("/api/deliveries/", delivery_payload, format="json").json()

    assert body["export_status"] == expected_status
    assert reason_fragment in body["export_status_reason"].lower()
    assert body["is_exportable"] is (risk_status == RiskStatus.CLEAR)


def test_unverified_export_reason_includes_registry_attempt_count(agent_api, make_plot, delivery_payload):
    plot = make_plot(risk_status=RiskStatus.UNVERIFIED)
    plot.risk_checks.create(attempt_number=1, outcome="error", error_message="unavailable")
    plot.risk_checks.create(attempt_number=2, outcome="timeout", error_message="timed out")
    delivery_payload["plot"] = plot.pk

    body = agent_api.post("/api/deliveries/", delivery_payload, format="json").json()

    assert body["export_status"] == "held"
    assert "registry unavailable after 2 attempts" in body["export_status_reason"].lower()


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


def test_default_delivery_date_is_the_same_date_used_for_price_selection(agent_api, delivery_payload):
    current = PriceSchedule.objects.get(is_active=True)
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    future = PriceSchedule.objects.create(season=current.season, effective_from=tomorrow)
    PriceEntry.objects.bulk_create(
        PriceEntry(
            schedule=future,
            grade=entry.grade,
            price_per_kg_rwf=Decimal("900.00") if entry.grade == "A" else entry.price_per_kg_rwf,
        )
        for entry in current.entries.all()
    )
    activate_schedule(future)
    del delivery_payload["delivered_on"]

    # Model defaults are separately evaluated at save time; simulate the request crossing midnight.
    date_field = Delivery._meta.get_field("delivered_on")
    with (
        patch("apps.deliveries.serializers.timezone.localdate", return_value=today),
        patch.object(date_field, "default", return_value=tomorrow) as model_date_default,
    ):
        response = agent_api.post("/api/deliveries/", delivery_payload, format="json")

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["delivered_on"] == today.isoformat()
    assert body["unit_price_rwf"] == str(current.entries.get(grade="A").price_per_kg_rwf)
    model_date_default.assert_not_called()


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
