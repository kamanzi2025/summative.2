"""Summative regression: deliveries stranded on a failed deforestation-risk check.

Staging scenario 3 (tests/staging/test_delivery_risk_check_stranding.py) found that a delivery on
a plot whose risk check never succeeds has no export status and no reason: only
`is_exportable: false`. These tests pin down the fix (BUG_REPORT.md, Scenario 3):

1. REGISTRY_API_URL is honored as config: until its provider contract is supplied, a configured
   endpoint fails closed and is recorded as a failed attempt (not silently replaced by the simulator).
2. Every delivery exposes `export_status` (eligible / held / rejected) and a human-readable
   `export_status_reason`, derived from its plot's *current* risk status.
"""

import pytest

from apps.deliveries.models import Delivery
from apps.registry.clients import RegistryUnavailable, get_registry_client
from apps.registry.models import AttemptOutcome, Plot, RiskStatus
from apps.registry.tasks import run_risk_check

pytestmark = pytest.mark.django_db

CONFIGURED_REGISTRY = "https://registry.example.invalid/api/risk-check"


def fail_every_attempt(plot: Plot) -> None:
    """Run the real task inline against an unreachable registry until retries run out."""
    run_risk_check.apply(args=[plot.pk])
    plot.refresh_from_db()


@pytest.fixture
def unsupported_registry(settings):
    settings.REGISTRY_API_URL = CONFIGURED_REGISTRY
    settings.REGISTRY_API_TIMEOUT = 2.0
    # If the simulator were (wrongly) used instead, it would answer "clear" every time.
    settings.RISK_REGISTRY_FAILURE_RATE = 0.0
    settings.RISK_REGISTRY_FLAG_RATE = 0.0


# --- 1. A configured registry never silently falls back to the simulator ----------------------


def test_configured_registry_does_not_fall_back_to_simulator(make_plot, unsupported_registry):
    plot = make_plot()

    fail_every_attempt(plot)

    attempts = list(plot.risk_checks.order_by("attempt_number"))
    assert attempts, "no risk-check attempt was recorded"
    assert {a.outcome for a in attempts} <= {AttemptOutcome.ERROR, AttemptOutcome.TIMEOUT}, (
        "REGISTRY_API_URL is configured but no provider contract is available, so no attempt may "
        f"succeed; got {[a.outcome for a in attempts]} (did the code fall back to the simulator?)"
    )
    assert all(a.error_message for a in attempts), "each failed attempt must say why it failed"
    assert plot.risk_status == RiskStatus.UNVERIFIED


def test_unsupported_registry_error_does_not_expose_configured_url(settings):
    secret_url = "https://user:private-token@registry.example.invalid/risk?key=private-token"
    settings.REGISTRY_API_URL = secret_url

    with pytest.raises(RegistryUnavailable) as raised:
        get_registry_client().check_plot(plot_code="P1", latitude=0, longitude=0)

    assert secret_url not in str(raised.value)
    assert "private-token" not in str(raised.value)


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
    agent_api, make_plot, record_delivery_on, unsupported_registry
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


def test_unknown_plot_risk_status_stays_held(agent_api, make_plot, record_delivery_on):
    plot = make_plot()
    Plot.objects.filter(pk=plot.pk).update(risk_status="unknown")
    plot.refresh_from_db()

    body = delivery_body(agent_api, record_delivery_on(plot))

    assert body["export_status"] == "held"
    assert "risk status is unknown" in body["export_status_reason"].lower()
    assert body["is_exportable"] is False
