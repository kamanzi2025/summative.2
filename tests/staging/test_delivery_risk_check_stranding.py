"""Staging Scenario 3: a failed risk check leaves delivery state observable.

The adapted scenario forces risk checks to fail, records a delivery, and
asserts that the response exposes a status-like field. The current implementation
holds deliveries from export while the plot is pending or unverified. The
dedicated tests in tests/test_risk_check_stranding.py assert the precise fields
and reason text. The seed's original import/collection errors are preserved in
docs/evidence/staging_raw_output.txt.
"""

# Ported from the summative/seed version (eeffead) to this project's layout. Changes, and why:
# - Imports: `core.models` -> `apps.registry.models`.
# - Plot payload: "Nyaruguru" is a district/station here, not a sector, so the plot is registered
#   in sector "Kigoma" (served by the Nyaruguru station, like seed plots K1/K2) at the same spot.
# - The plot POST runs inside django_capture_on_commit_callbacks(execute=True), with
#   run_risk_check.delay routed to run_risk_check.apply so the real task and retry path run inline.
# - The registry wire contract is not supplied, so a configured REGISTRY_API_URL must fail closed
#   instead of silently substituting the simulator. The failed-attempt assertion below checks this.
# - Added a setup guard asserting the risk check really failed (every attempt an error, plot not
#   clear), so the scenario cannot silently pass because the registry happened to answer.
# STATUS_LIKE_FIELDS and the final assertion are unchanged.

from unittest.mock import patch

import pytest

from apps.registry.models import Farmer, Plot, RiskStatus
from apps.registry.tasks import run_risk_check

STATUS_LIKE_FIELDS = {"status", "state", "export_status", "risk_check_status", "rejection_reason"}


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
