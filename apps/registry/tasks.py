"""Background deforestation-risk checks.

Flow: POST /api/plots/ -> on commit -> run_risk_check.delay(plot_id) -> worker calls the
registry -> plot becomes clear/flagged. Transient failures retry with exponential backoff and
jitter; when retries run out the plot becomes `unverified` and the periodic sweeper retries later.
"""

import logging

from celery import Task, shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings

from . import services
from .clients import RegistryError, RegistryTimeout, get_registry_client
from .models import Plot, RiskStatus

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    acks_late=True,
    autoretry_for=(RegistryError,),
    # Countdown before retry n is random(0, min(60 * 2**n, 3600)) seconds: 60 s, 120 s, 240 s ...
    # capped at 1 h. Eight retries span up to ~3 h (~1.5 h on average with full jitter), which
    # rides out a typical registry outage; the sweeper covers anything longer.
    retry_backoff=settings.RISK_CHECK_BACKOFF_SECONDS,
    retry_backoff_max=3600,
    retry_jitter=True,
    max_retries=settings.RISK_CHECK_MAX_RETRIES,
    # Backstop above the client's own timeout so a hung call can't pin a worker forever.
    soft_time_limit=services.ATTEMPT_SOFT_TIME_LIMIT_SECONDS,
)
def run_risk_check(self: Task, plot_id: int) -> str:
    plot = Plot.objects.filter(pk=plot_id).first()
    if plot is None:
        logger.warning("risk_check.plot_missing", extra={"plot_id": plot_id})
        return "missing"
    # Idempotent: duplicate deliveries of this message (acks_late, sweeper) are harmless.
    if plot.risk_status in services.SETTLED_STATUSES:
        logger.info("risk_check.skipped", extra={"plot_id": plot_id, "risk_status": plot.risk_status})
        return plot.risk_status

    attempt = services.start_attempt(plot, task_id=self.request.id or "")
    log_ctx = {"plot_id": plot_id, "attempt": attempt.attempt_number, "retries": self.request.retries}
    try:
        try:
            assessment = get_registry_client().check_plot(
                plot_code=plot.plot_code, latitude=plot.latitude, longitude=plot.longitude
            )
        except SoftTimeLimitExceeded:
            # The client ignored its own timeout; record it as a timeout and retry like one.
            raise RegistryTimeout(
                f"registry call exceeded the {services.ATTEMPT_SOFT_TIME_LIMIT_SECONDS}s task time limit"
            ) from None
    except RegistryError as exc:
        services.finish_attempt(attempt, outcome=exc.outcome, error_message=str(exc))
        logger.info(
            "risk_check.attempt",
            extra={**log_ctx, "outcome": exc.outcome, "duration_ms": attempt.duration_ms, "error": str(exc)},
        )
        if self.max_retries is not None and self.request.retries >= self.max_retries:
            services.mark_unverified(plot)
            logger.warning("risk_check.exhausted", extra={**log_ctx, "risk_status": RiskStatus.UNVERIFIED})
            return RiskStatus.UNVERIFIED
        raise  # autoretry_for schedules the next attempt with backoff + jitter

    outcome = services.attempt_outcome_for(assessment)
    services.finish_attempt(attempt, outcome=outcome)
    services.apply_assessment(plot, assessment)
    logger.info(
        "risk_check.attempt",
        extra={**log_ctx, "outcome": outcome, "duration_ms": attempt.duration_ms, "reference": assessment.reference},
    )
    return plot.risk_status


@shared_task
def requeue_stale_risk_checks() -> int:
    """Celery beat job: re-enqueue plots stuck in pending/unverified so hours-long registry
    outages (or a missed enqueue during a broker outage) recover without a human. It also
    closes attempts left `running` by a worker that died mid-call, so the audit trail stays true."""
    abandoned = services.close_abandoned_attempts()
    plot_ids = services.stale_plot_ids()
    queued = sum(services.enqueue_risk_check(plot_id) for plot_id in plot_ids)
    logger.info(
        "risk_check.requeue_stale",
        extra={"found": len(plot_ids), "queued": queued, "abandoned_attempts": abandoned},
    )
    return queued
