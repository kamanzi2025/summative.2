"""Business operations for farmers, plots and risk checks. Views and tasks call these."""

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from .clients import RiskAssessment
from .models import AttemptOutcome, Farmer, Plot, RiskCheckAttempt, RiskStatus

logger = logging.getLogger(__name__)

SETTLED_STATUSES = frozenset({RiskStatus.CLEAR, RiskStatus.FLAGGED})


def register_farmer(data: dict[str, Any]) -> Farmer:
    return Farmer.objects.create(**data)


def register_plot(data: dict[str, Any]) -> Plot:
    """Create a plot as `pending` and queue its risk check once the row is committed.

    The registry is never called here: registration must answer in well under a second on 2G,
    while the registry can take 40 seconds or be down for hours.
    """
    with transaction.atomic():
        plot = Plot.objects.create(risk_status=RiskStatus.PENDING, **data)
        transaction.on_commit(lambda: enqueue_risk_check(plot.pk))
    return plot


def enqueue_risk_check(plot_id: int) -> bool:
    """Publish the risk-check task. A broker outage must not fail the farmer's registration:
    the plot stays `pending` and `requeue_stale_risk_checks` picks it up later."""
    from .tasks import run_risk_check

    try:
        run_risk_check.delay(plot_id)
    except Exception:  # any broker/transport failure is handled the same way
        logger.exception("risk_check.enqueue_failed", extra={"plot_id": plot_id})
        return False
    logger.info("risk_check.enqueued", extra={"plot_id": plot_id})
    return True


def start_attempt(plot: Plot, task_id: str) -> RiskCheckAttempt:
    number = RiskCheckAttempt.objects.filter(plot=plot).count() + 1
    return RiskCheckAttempt.objects.create(plot=plot, attempt_number=number, task_id=task_id)


def finish_attempt(attempt: RiskCheckAttempt, outcome: str, error_message: str = "") -> RiskCheckAttempt:
    attempt.finished_at = timezone.now()
    attempt.duration_ms = int((attempt.finished_at - attempt.started_at).total_seconds() * 1000)
    attempt.outcome = outcome
    attempt.error_message = error_message
    attempt.save(update_fields=["finished_at", "duration_ms", "outcome", "error_message"])
    return attempt


def apply_assessment(plot: Plot, assessment: RiskAssessment) -> Plot:
    plot.risk_status = RiskStatus(assessment.status)
    plot.risk_checked_at = timezone.now()
    plot.save(update_fields=["risk_status", "risk_checked_at"])
    return plot


def mark_unverified(plot: Plot) -> Plot:
    """Retries are exhausted. `unverified` means "no answer yet", not a verdict."""
    if plot.risk_status not in SETTLED_STATUSES:
        plot.risk_status = RiskStatus.UNVERIFIED
        plot.save(update_fields=["risk_status"])
    return plot


def stale_plot_ids(limit: int = 500) -> list[int]:
    """Plots still waiting on the registry with no attempt inside the stale window."""
    cutoff = timezone.now() - timedelta(hours=settings.RISK_CHECK_STALE_HOURS)
    recent_attempt = RiskCheckAttempt.objects.filter(plot=OuterRef("pk"), started_at__gte=cutoff)
    return list(
        Plot.objects.filter(risk_status__in=[RiskStatus.PENDING, RiskStatus.UNVERIFIED], created_at__lt=cutoff)
        .exclude(Exists(recent_attempt))
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )


def attempt_outcome_for(assessment: RiskAssessment) -> str:
    return AttemptOutcome.CLEAR if assessment.status == "clear" else AttemptOutcome.FLAGGED
