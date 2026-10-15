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

# Ported from the summative/seed version (eeffead) to this project's layout. Changes, and why:
# - Imports: `core.models` -> `apps.registry.models`.
# - Plot payload: "Nyaruguru" is a district/station here, not a sector, so the plot is registered
#   in sector "Kigoma" (served by the Nyaruguru station, like seed plots K1/K2) at the same spot.
# - Making the failure real: the seed relied on REGISTRY_API_URL alone, but in tests the risk check
#   would never run (on_commit hooks do not fire inside a test transaction and there is no
#   worker). So the plot POST runs inside django_capture_on_commit_callbacks(execute=True) with
#   run_risk_check.delay routed to run_risk_check.apply: the real task, its retries and its client
#   run inline. REGISTRY_API_URL is still pointed at a refused port (as in the seed), and
#   RISK_REGISTRY_FAILURE_RATE=1.0 makes the simulated registry fail too, so the registry fails
#   whichever client is configured.
# - Added a setup guard asserting the risk check really failed (every attempt an error, plot not
#   clear), so the scenario cannot silently pass because the registry happened to answer.
# STATUS_LIKE_FIELDS and the final assertion are unchanged.
# Marked xfail(strict=True) until the fix: the failure is genuine (see BUG_REPORT.md), and strict
# means the suite goes red as soon as the fix lands, forcing the marker to be removed.

from unittest.mock import patch

import pytest

from apps.registry.models import Farmer, Plot, RiskStatus
from apps.registry.tasks import run_risk_check

STATUS_LIKE_FIELDS = {"status", "state", "export_status", "risk_check_status", "rejection_reason"}


@pytest.mark.xfail(
    strict=True,
    reason="Known Summative bug: a delivery on a plot whose risk check failed has no export status or reason",
)
@pytest.mark.django_db
def test_delivery_reaches_an_observable_state_after_failed_risk_check(
    as_role, settings, django_capture_on_commit_callbacks
):
    # Points any real registry integration at an address that will refuse
    # the connection, forcing a failure. Inert against implementations that
    # don't yet read this setting -- see module docstring.
    settings.REGISTRY_API_URL = "http://127.0.0.1:1/unreachable-registry"
    settings.RISK_REGISTRY_FAILURE_RATE = 1.0

    client = as_role("field_agent_user")
    farmer = Farmer.objects.first()
    assert farmer is not None, "seed_rbac_fixtures did not create the seed farmer"

    with (
        patch.object(run_risk_check, "delay", side_effect=lambda plot_id: run_risk_check.apply(args=[plot_id])),
        django_capture_on_commit_callbacks(execute=True),
    ):
        plot_response = client.post(
            "/api/plots/",
            {
                "farmer": farmer.id,
                "plot_code": "KWA-STAGING-RISK-01",
                "sector": "Kigoma",
                "washing_station": "Nyaruguru",
                "latitude": "-2.550000",
                "longitude": "29.720000",
                "area_hectares": "1.00",
            },
            format="json",
        )
    assert plot_response.status_code == 201, plot_response.content
    plot_id = plot_response.json()["id"]

    plot = Plot.objects.get(pk=plot_id)
    outcomes = set(plot.risk_checks.values_list("outcome", flat=True))
    assert outcomes and outcomes <= {"error", "timeout"}, f"registry was not forced to fail: {outcomes}"
    assert plot.risk_status != RiskStatus.CLEAR

    delivery_response = client.post(
        "/api/deliveries/",
        {
            "plot": plot_id,
            "washing_station": "Nyaruguru",
            "weight_kg": "10.00",
            "grade": "A",
            "delivered_on": "2026-09-01",
        },
        format="json",
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
