"""Summative regression: deliveries stranded on a failed deforestation-risk check.

Staging scenario 3 (tests/staging/test_delivery_risk_check_stranding.py) found that a delivery on
a plot whose risk check never succeeds has no export status and no reason: only
`is_exportable: false`. These tests pin down the fix (BUG_REPORT.md, Scenario 3):

1. REGISTRY_API_URL is real config: when it is set, the worker calls that registry, and an
   unreachable registry is recorded as a failed attempt (not silently replaced by the simulator).
2. Every delivery exposes `export_status` (eligible / held / rejected) and a human-readable
   `export_status_reason`, derived from its plot's *current* risk status.
"""

import pytest

from apps.deliveries.models import Delivery
from apps.registry.models import AttemptOutcome, Plot, RiskStatus
from apps.registry.tasks import run_risk_check

pytestmark = pytest.mark.django_db

UNREACHABLE_REGISTRY = "http://127.0.0.1:1/unreachable-registry"


def fail_every_attempt(plot: Plot) -> None:
    """Run the real task inline against an unreachable registry until retries run out."""
    run_risk_check.apply(args=[plot.pk])
    plot.refresh_from_db()


@pytest.fixture
def unreachable_registry(settings):
    settings.REGISTRY_API_URL = UNREACHABLE_REGISTRY
    settings.REGISTRY_API_TIMEOUT = 2.0
    # If the simulator were (wrongly) used instead, it would answer "clear" every time.
    settings.RISK_REGISTRY_FAILURE_RATE = 0.0
    settings.RISK_REGISTRY_FLAG_RATE = 0.0


# --- 1. REGISTRY_API_URL selects a real registry client ----------------------------------------


def test_unreachable_registry_url_records_failed_attempts(make_plot, unreachable_registry):
    plot = make_plot()

    fail_every_attempt(plot)

    attempts = list(plot.risk_checks.order_by("attempt_number"))
    assert attempts, "no risk-check attempt was recorded"
    assert {a.outcome for a in attempts} <= {AttemptOutcome.ERROR, AttemptOutcome.TIMEOUT}, (
        "REGISTRY_API_URL is set to a refused port, so no attempt may succeed; "
        f"got {[a.outcome for a in attempts]} (is the simulator still being used?)"
    )
    assert all(a.error_message for a in attempts), "each failed attempt must say why it failed"
    assert plot.risk_status == RiskStatus.UNVERIFIED


# --- 2. Deliveries expose an export status and a reason ----------------------------------------


def delivery_body(api, delivery: Delivery) -> dict:
    response = api.get(f"/api/deliveries/{delivery.pk}/")
    assert response.status_code == 200, response.content
    return response.json()


@pytest.fixture
def record_delivery_on(agent_api, delivery_payload):
    def _record(plot: Plot) -> Delivery:
        response = agent_api.post("/api/deliveries/", {**delivery_payload, "plot": plot.pk}, format="json")
        assert response.status_code == 201, response.content
        return Delivery.objects.get(pk=response.json()["id"])

    return _record


def test_delivery_on_plot_with_failed_risk_check_is_held_with_reason(
    agent_api, make_plot, record_delivery_on, unreachable_registry
):
    plot = make_plot()
    fail_every_attempt(plot)
    attempts = plot.risk_checks.count()

    body = delivery_body(agent_api, record_delivery_on(plot))

    assert body["export_status"] == "held"
    reason = body["export_status_reason"].lower()
    assert "registry unavailable" in reason
    assert f"{attempts} attempts" in reason, f"reason should say how many attempts failed: {reason!r}"


@pytest.mark.parametrize(
    ("risk_status", "export_status", "reason_mentions"),
    [
        (RiskStatus.CLEAR, "eligible", "clear"),
        (RiskStatus.PENDING, "held", "pending"),
        (RiskStatus.FLAGGED, "rejected", "flagged"),
    ],
)
def test_export_status_and_reason_follow_plot_risk_status(
    agent_api, make_plot, record_delivery_on, risk_status, export_status, reason_mentions
):
    body = delivery_body(agent_api, record_delivery_on(make_plot(risk_status=risk_status)))

    assert body["export_status"] == export_status
    assert reason_mentions in body["export_status_reason"].lower()


def test_export_status_follows_the_plots_current_status_not_the_snapshot(agent_api, make_plot, record_delivery_on):
    plot = make_plot(risk_status=RiskStatus.PENDING)
    delivery = record_delivery_on(plot)
    assert delivery_body(agent_api, delivery)["export_status"] == "held"

    Plot.objects.filter(pk=plot.pk).update(risk_status=RiskStatus.CLEAR)

    body = delivery_body(agent_api, delivery)
    assert body["export_status"] == "eligible"
    # The snapshot still records what was known when the cherry was weighed.
    assert body["plot_risk_status_at_delivery"] == "pending"


def test_delivery_feed_rows_carry_export_status_and_reason(agent_api, make_plot, record_delivery_on):
    record_delivery_on(make_plot(risk_status=RiskStatus.FLAGGED))

    rows = agent_api.get("/api/deliveries/").json()["results"]

    assert rows, "feed returned no deliveries"
    assert {"export_status", "export_status_reason"} <= set(rows[0])
    assert rows[0]["export_status"] == "rejected"
