"""Task 3: the background deforestation-risk check."""

import random
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.db import IntegrityError, transaction
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


@pytest.mark.parametrize(("retries", "cap"), [(0, 60), (3, 480), (7, 3600)])
def test_retry_uses_capped_exponential_backoff(make_plot, retries, cap):
    plot = make_plot()
    patcher, _ = registry_returning(RegistryUnavailable("503"))
    with patcher, patch.object(run_risk_check, "retry", side_effect=RuntimeError("stop")) as retry:
        run_risk_check.apply(args=[plot.pk], retries=retries)
    kwargs = retry.call_args.kwargs
    assert isinstance(kwargs["exc"], RegistryUnavailable)
    # retry_backoff=60 with full jitter: countdown is random in [0, min(60 * 2**retries, 3600)].
    assert 0 <= kwargs["countdown"] <= cap


def test_retry_schedule_spans_hours_not_minutes():
    """Worst case across all retries must outlast a multi-hour outage (ADR-001)."""
    from celery.utils.time import get_exponential_backoff_interval

    worst = sum(
        get_exponential_backoff_interval(factor=60, retries=n, maximum=3600, full_jitter=False)
        for n in range(run_risk_check.max_retries)
    )
    assert worst == 60 + 120 + 240 + 480 + 960 + 1920 + 3600 + 3600  # 10,980 s, about 3 hours


def test_task_time_limit_is_recorded_as_timeout_and_retried(make_plot):
    plot = make_plot()
    patcher, _ = registry_returning(SoftTimeLimitExceeded(), CLEAR)
    with patcher:
        run_risk_check.apply(args=[plot.pk])
    plot.refresh_from_db()
    assert outcomes(plot) == ["timeout", "clear"]
    assert "time limit" in plot.risk_checks.get(attempt_number=1).error_message
    assert plot.risk_status == RiskStatus.CLEAR


def test_attempt_numbers_continue_after_existing_attempts(make_plot):
    plot = make_plot()
    plot.risk_checks.create(attempt_number=3, outcome="error")
    patcher, _ = registry_returning(CLEAR)
    with patcher:
        run_risk_check.apply(args=[plot.pk])
    assert list(plot.risk_checks.values_list("attempt_number", flat=True)) == [3, 4]


def test_attempt_numbers_are_unique_per_plot(make_plot):
    plot = make_plot()
    plot.risk_checks.create(attempt_number=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        plot.risk_checks.create(attempt_number=1)


def test_sweeper_closes_attempts_abandoned_by_a_dead_worker(make_plot):
    plot = make_plot(risk_status=RiskStatus.CLEAR)
    dead = plot.risk_checks.create(attempt_number=1, started_at=timezone.now() - timedelta(hours=1))
    live = plot.risk_checks.create(attempt_number=2)
    with patch("apps.registry.tasks.run_risk_check.delay"):
        requeue_stale_risk_checks.apply()
    dead.refresh_from_db()
    live.refresh_from_db()
    assert dead.outcome == AttemptOutcome.ERROR and "abandoned" in dead.error_message
    assert live.outcome == AttemptOutcome.RUNNING


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


def test_status_reports_the_risk_check_backlog(anon_api, make_plot, settings):
    """A stalled worker is visible on /api/status/ without failing the liveness probe."""
    settings.RISK_CHECK_STALE_HOURS = 6
    settings.RISK_CHECK_MANUAL_REVIEW_DAYS = 7
    make_plot()  # fresh pending: not stale yet
    make_plot(created_at=timezone.now() - timedelta(hours=7))  # stale pending
    make_plot(created_at=timezone.now() - timedelta(days=8), risk_status=RiskStatus.UNVERIFIED)
    make_plot(risk_status=RiskStatus.CLEAR)

    body = anon_api.get("/api/status/").json()

    assert body["status"] == "ok"
    backlog = body["risk_checks"]
    assert backlog["pending"] == 2
    assert backlog["unverified"] == 1
    assert backlog["stale"] == 2
    assert backlog["requires_manual_review"] == 1
    assert backlog["healthy"] is False


def test_status_is_healthy_with_no_backlog(anon_api, db):
    backlog = anon_api.get("/api/status/").json()["risk_checks"]
    assert backlog["stale"] == 0
    assert backlog["healthy"] is True
