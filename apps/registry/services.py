"""Business operations for farmers, plots and risk checks. Views and tasks call these."""

import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, Max, OuterRef
from django.utils import timezone

from .clients import RiskAssessment
from .models import AttemptOutcome, Farmer, Plot, RiskCheckAttempt, RiskStatus
from .validators import normalise_rwandan_phone

logger = logging.getLogger(__name__)

SETTLED_STATUSES = frozenset({RiskStatus.CLEAR, RiskStatus.FLAGGED})
# Hard ceiling for one registry call inside the worker (client timeout + margin).
ATTEMPT_SOFT_TIME_LIMIT_SECONDS = int(settings.REGISTRY_API_TIMEOUT) + 30


def register_farmer(data: dict[str, Any]) -> Farmer:
    return Farmer.objects.create(**data)


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def find_farmer_replay(data: dict[str, Any]) -> Farmer | None:
    member_number = data.get("member_number")
    if not isinstance(member_number, str) or not member_number.strip():
        return None
    return Farmer.objects.select_related("home_station").filter(member_number=member_number.strip()).first()


def farmer_replay_mismatches(farmer: Farmer, data: dict[str, Any]) -> list[str]:
    """Fields where a resent registration disagrees with the stored farmer (after normalising)."""
    mismatched = []
    if _text(data.get("full_name")) != farmer.full_name:
        mismatched.append("full_name")
    if normalise_rwandan_phone(_text(data.get("phone"))) != farmer.phone:
        mismatched.append("phone")
    if (_text(data.get("national_id")) or None) != farmer.national_id:
        mismatched.append("national_id")
    if _text(data.get("cooperative")) != farmer.cooperative:
        mismatched.append("cooperative")
    return mismatched


def find_plot_replay(data: dict[str, Any]) -> Plot | None:
    plot_code = data.get("plot_code")
    if not isinstance(plot_code, str) or not plot_code.strip():
        return None
    return Plot.objects.select_related("sector", "washing_station").filter(plot_code=plot_code.strip()).first()


def plot_replay_mismatches(plot: Plot, data: dict[str, Any]) -> list[str]:
    """Fields where a resent plot registration disagrees with the stored plot."""
    mismatched = []
    if _text(data.get("farmer")) != str(plot.farmer_id):
        mismatched.append("farmer")
    if _text(data.get("sector")).lower() != plot.sector.name.lower():
        mismatched.append("sector")
    if _text(data.get("washing_station")).lower() != plot.washing_station.name.lower():
        mismatched.append("washing_station")
    for field in ("latitude", "longitude", "area_hectares"):
        if _decimal(data.get(field)) != getattr(plot, field):
            mismatched.append(field)
    return mismatched


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


@transaction.atomic
def start_attempt(plot: Plot, task_id: str) -> RiskCheckAttempt:
    """Open the next numbered attempt. The plot row lock serialises concurrent tasks for the same
    plot (e.g. a late retry overlapping a sweeper requeue); the unique constraint backs it up."""
    Plot.objects.select_for_update().filter(pk=plot.pk).exists()
    last = RiskCheckAttempt.objects.filter(plot=plot).aggregate(n=Max("attempt_number"))["n"] or 0
    return RiskCheckAttempt.objects.create(plot=plot, attempt_number=last + 1, task_id=task_id)


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


def close_abandoned_attempts() -> int:
    """Mark attempts still `running` long after any live call could last as errors.

    Happens when a worker is killed mid-call (deploy, OOM); acks_late redelivers the message, but
    the old row would otherwise claim to be running forever.
    """
    cutoff = timezone.now() - timedelta(seconds=ATTEMPT_SOFT_TIME_LIMIT_SECONDS * 2)
    return RiskCheckAttempt.objects.filter(outcome=AttemptOutcome.RUNNING, started_at__lt=cutoff).update(
        outcome=AttemptOutcome.ERROR,
        finished_at=timezone.now(),
        error_message="abandoned: worker stopped before the registry call finished",
    )


def attempt_outcome_for(assessment: RiskAssessment) -> str:
    return AttemptOutcome.CLEAR if assessment.status == "clear" else AttemptOutcome.FLAGGED
