from unittest.mock import patch

import pytest
from kombu.exceptions import OperationalError

from apps.registry.models import Plot, RiskStatus

pytestmark = pytest.mark.django_db


def test_create_plot_returns_pending_and_enqueues_on_commit(api, plot_payload, django_capture_on_commit_callbacks):
    with (
        patch("apps.registry.tasks.run_risk_check.delay") as delay,
        patch("apps.registry.tasks.get_registry_client") as registry,
    ):
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            response = api.post("/api/plots/", plot_payload, format="json")
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


def test_broker_outage_does_not_fail_registration(api, plot_payload, django_capture_on_commit_callbacks):
    with (
        patch("apps.registry.tasks.run_risk_check.delay", side_effect=OperationalError("redis down")),
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = api.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 201
    assert Plot.objects.get().risk_status == RiskStatus.PENDING


def test_list_plots_filters(api, make_plot, make_farmer, kamonyi):
    owner = make_farmer()
    mine = make_plot(farmer=owner, risk_status=RiskStatus.CLEAR)
    make_plot(risk_status=RiskStatus.PENDING)
    other_station = make_plot(washing_station=kamonyi)

    def ids(query: str) -> list[int]:
        return [row["id"] for row in api.get(f"/api/plots/?{query}").json()["results"]]

    assert ids(f"farmer={owner.pk}") == [mine.pk]
    assert ids("risk_status=clear") == [mine.pk]
    assert ids("washing_station=Kamonyi") == [other_station.pk]
    assert len(ids("sector=kigoma")) == 3


def test_risk_check_history_endpoint(api, make_plot):
    plot = make_plot()
    plot.risk_checks.create(attempt_number=1, outcome="error", error_message="503")
    plot.risk_checks.create(attempt_number=2, outcome="clear")
    history = api.get(f"/api/plots/{plot.pk}/risk-checks/").json()
    assert [(a["attempt_number"], a["outcome"]) for a in history] == [(1, "error"), (2, "clear")]


def test_missing_sector_is_rejected(api, plot_payload):
    del plot_payload["sector"]
    response = api.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"]["sector"] == ["This field is required."]


def test_unknown_sector_is_rejected(api, plot_payload):
    plot_payload["sector"] = "Atlantis"
    response = api.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 400
    assert "sector" in response.json()["error"]["details"]


@pytest.mark.parametrize(
    ("field", "value"),
    # Kampala's latitude, the equator, Nairobi's longitude, eastern DRC's longitude.
    [("latitude", "0.347596"), ("latitude", "0.0"), ("longitude", "36.817223"), ("longitude", "28.0")],
)
def test_coordinates_outside_rwanda_are_rejected(api, plot_payload, field, value):
    plot_payload[field] = value
    response = api.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 400
    assert field in response.json()["error"]["details"]


@pytest.mark.parametrize("area", ["0", "-0.5", "51"])
def test_area_out_of_range_is_rejected(api, plot_payload, area):
    plot_payload["area_hectares"] = area
    response = api.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 400
    assert "area_hectares" in response.json()["error"]["details"]


def test_duplicate_plot_code_is_rejected(api, plot_payload, make_plot):
    make_plot(plot_code="KWA-P-0417-A")
    response = api.post("/api/plots/", plot_payload, format="json")
    assert response.status_code == 400
    assert "plot_code" in response.json()["error"]["details"]


def test_manual_review_queue_filter(api, make_plot, settings):
    from datetime import timedelta

    from django.utils import timezone

    settings.RISK_CHECK_MANUAL_REVIEW_DAYS = 7
    overdue = make_plot(risk_status=RiskStatus.UNVERIFIED, created_at=timezone.now() - timedelta(days=9))
    make_plot(risk_status=RiskStatus.UNVERIFIED)  # unverified, but still inside the window
    make_plot(risk_status=RiskStatus.CLEAR, created_at=timezone.now() - timedelta(days=9))

    queue = api.get("/api/plots/?requires_manual_review=true").json()["results"]
    assert [row["id"] for row in queue] == [overdue.pk]
    assert queue[0]["requires_manual_review"] is True
    assert len(api.get("/api/plots/?requires_manual_review=false").json()["results"]) == 2
