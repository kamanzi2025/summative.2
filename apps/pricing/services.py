from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import Conflict

from .models import PriceEntry, PriceSchedule


def get_active_schedule(on: date | None = None) -> PriceSchedule | None:
    """Select globally by effective date, refusing equal-date ambiguity across seasons."""
    on = on or timezone.localdate()
    candidates = list(
        PriceSchedule.objects.filter(is_active=True, effective_from__lte=on)
        .prefetch_related("entries")
        .order_by("-effective_from")[:2]
    )
    if not candidates:
        return None
    if len(candidates) == 2 and candidates[0].effective_from == candidates[1].effective_from:
        raise Conflict("Active price schedules share the same effective date.")
    return candidates[0]


def get_active_price(grade: str, on: date | None = None) -> PriceEntry | None:
    schedule = get_active_schedule(on)
    if schedule is None:
        return None
    return next((entry for entry in schedule.entries.all() if entry.grade == grade), None)


@transaction.atomic
def activate_schedule(schedule: PriceSchedule) -> PriceSchedule:
    """Schedule prices from their effective date while retaining earlier active schedules.

    `get_active_schedule()` selects the most recent effective schedule for a date. The database
    constraint permits only one active schedule per effective date globally.
    """
    cross_season_conflict = (
        PriceSchedule.objects.filter(
            is_active=True,
            effective_from=schedule.effective_from,
        )
        .exclude(pk=schedule.pk)
        .exclude(season=schedule.season)
    )
    if cross_season_conflict.exists():
        raise Conflict("An active schedule from another season has the same effective date.")

    PriceSchedule.objects.filter(
        season=schedule.season,
        effective_from=schedule.effective_from,
        is_active=True,
    ).exclude(pk=schedule.pk).update(is_active=False)
    schedule.is_active = True
    schedule.save(update_fields=["is_active"])
    return schedule
