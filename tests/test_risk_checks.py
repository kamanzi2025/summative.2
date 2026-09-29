"""Task 3: the background deforestation-risk check."""

import random
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.registry.clients import (
    RegistryTimeout,
    RegistryUnavailable,
    RiskAssessment,
    SimulatedRiskRegistry,
)
from apps.registry.models import AttemptOutcome, Plot, RiskStatus
from apps.registry.tasks import requeue_stale_risk_checks, run_risk_check

pytestmark = pytest.mark.django_db

CLEAR = RiskAssessment(status="clear", reference="SIM-1")
FLAGGED = RiskAssessment(status="flagged", reference="SIM-1")


def registry_returning(*results):
    client = MagicMock()
    client.check_plot.side_effect = list(results)
    return patch("apps.registry.tasks.get_registry_client", return_value=client), client


def outcomes(plot: Plot) -> list[str]:
    return list(plot.risk_checks.order_by("attempt_number").values_list("outcome", flat=True))


def test_success_records_attempt_and_sets_status(make_plot):
    plot = make_plot()
    patcher, _ = registry_returning(CLEAR)
    with patcher:
        result = run_risk_check.apply(args=[plot.pk])
    plot.refresh_from_db()
    assert result.get() == "clear"
    assert plot.risk_status == RiskStatus.CLEAR
    assert plot.risk_checked_at is not None
    attempt = plot.risk_checks.get()
    assert attempt.outcome == AttemptOutcome.CLEAR
    assert attempt.finished_at is not None and attempt.duration_ms is not None


def test_flagged_result(make_plot):
    plot = make_plot()
    patcher, _ = registry_returning(FLAGGED)
    with patcher:
        run_risk_check.apply(args=[plot.pk])
    plot.refresh_from_db()
    assert plot.risk_status == RiskStatus.FLAGGED


def test_failure_records_error_attempt_and_retries(make_plot):
    plot = make_plot()
    patcher, client = registry_returning(RegistryUnavailable("503"), RegistryTimeout("slow"), CLEAR)
    with patcher:
        run_risk_check.apply(args=[plot.pk])  # eager apply() runs the retries inline
    plot.refresh_from_db()
    assert client.check_plot.call_count == 3
    assert outcomes(plot) == ["error", "timeout", "clear"]
    assert plot.risk_checks.get(attempt_number=1).error_message == "503"
    assert plot.risk_status == RiskStatus.CLEAR


def test_retry_uses_exponential_backoff(make_plot):
    plot = make_plot()
    patcher, _ = registry_returning(RegistryUnavailable("503"))
    with patcher, patch.object(run_risk_check, "retry", side_effect=RuntimeError("stop")) as retry:
        run_risk_check.apply(args=[plot.pk], retries=3)
    kwargs = retry.call_args.kwargs
    assert isinstance(kwargs["exc"], RegistryUnavailable)
    # retry_backoff=True with full jitter: countdown is in [0, 2**3] seconds.
    assert 0 <= kwargs["countdown"] <= 8


def test_exhausted_retries_mark_plot_unverified(make_plot):
    plot = make_plot()
    patcher, client = registry_returning(*[RegistryUnavailable("503")] * 20)
    with patcher:
        result = run_risk_check.apply(args=[plot.pk])
    plot.refresh_from_db()
    assert plot.risk_status == RiskStatus.UNVERIFIED
    assert client.check_plot.call_count == run_risk_check.max_retries + 1
    assert set(outcomes(plot)) == {"error"}
    assert result.successful()


def test_task_is_idempotent_for_settled_plots(make_plot):
    plot = make_plot(risk_status=RiskStatus.CLEAR)
    patcher, client = registry_returning(FLAGGED)
    with patcher:
        assert run_risk_check.apply(args=[plot.pk]).get() == "clear"
    client.check_plot.assert_not_called()
    assert not plot.risk_checks.exists()


def test_missing_plot_is_ignored():
    assert run_risk_check.apply(args=[987654]).get() == "missing"


def test_sweeper_requeues_only_stale_unsettled_plots(make_plot, settings):
    settings.RISK_CHECK_STALE_HOURS = 6
    old = timezone.now() - timedelta(hours=12)
    stale_pending = make_plot(created_at=old)
    stale_unverified = make_plot(created_at=old, risk_status=RiskStatus.UNVERIFIED)
    make_plot()  # recent pending: its own retries are still running
    make_plot(created_at=old, risk_status=RiskStatus.CLEAR)
    recently_tried = make_plot(created_at=old)
    recently_tried.risk_checks.create(attempt_number=1, outcome="error")

    with patch("apps.registry.tasks.run_risk_check.delay") as delay:
        assert requeue_stale_risk_checks.apply().get() == 2
    assert {c.args[0] for c in delay.call_args_list} == {stale_pending.pk, stale_unverified.pk}


def test_unverified_plot_needs_manual_review_after_policy_window(make_plot, settings):
    settings.RISK_CHECK_MANUAL_REVIEW_DAYS = 7
    assert make_plot(
        created_at=timezone.now() - timedelta(days=8), risk_status=RiskStatus.UNVERIFIED
    ).requires_manual_review
    assert not make_plot(
        created_at=timezone.now() - timedelta(days=2), risk_status=RiskStatus.UNVERIFIED
    ).requires_manual_review
    assert not make_plot(
        created_at=timezone.now() - timedelta(days=8), risk_status=RiskStatus.CLEAR
    ).requires_manual_review


class TestSimulatedRegistry:
    def make(self, **overrides):
        options = {
            "min_latency": 0.0,
            "max_latency": 0.0,
            "failure_rate": 0.0,
            "flag_rate": 0.0,
            "timeout": 30.0,
            "rng": random.Random(7),
            "sleep": MagicMock(),
        }
        options.update(overrides)
        return SimulatedRiskRegistry(**options)

    def check(self, registry):
        return registry.check_plot(plot_code="P1", latitude=-2.54, longitude=29.71)

    def test_clear_when_healthy(self):
        assert self.check(self.make()).status == "clear"

    def test_flags(self):
        assert self.check(self.make(flag_rate=1.0)).status == "flagged"

    def test_outage(self):
        with pytest.raises(RegistryUnavailable):
            self.check(self.make(failure_rate=1.0))

    def test_timeout_when_latency_exceeds_budget(self):
        sleep = MagicMock()
        with pytest.raises(RegistryTimeout):
            self.check(self.make(min_latency=40, max_latency=40, timeout=5, sleep=sleep))
        sleep.assert_called_once_with(5)
