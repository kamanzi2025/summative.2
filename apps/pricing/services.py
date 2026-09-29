from datetime import date

from django.db import transaction
from django.utils import timezone

from .models import PriceEntry, PriceSchedule


def get_active_schedule(on: date | None = None) -> PriceSchedule | None:
    """The schedule stations pay from today: active, already in effect, most recent first."""
    on = on or timezone.localdate()
    return (
        PriceSchedule.objects.filter(is_active=True, effective_from__lte=on)
        .prefetch_related("entries")
        .order_by("-effective_from", "-id")
        .first()
    )


def get_active_price(grade: str, on: date | None = None) -> PriceEntry | None:
    return (
        PriceEntry.objects.select_related("schedule")
        .filter(schedule__is_active=True, schedule__effective_from__lte=on or timezone.localdate(), grade=grade)
        .order_by("-schedule__effective_from", "-schedule_id")
        .first()
    )


@transaction.atomic
def activate_schedule(schedule: PriceSchedule) -> PriceSchedule:
    """Make `schedule` the season's only active schedule (enforced by a DB constraint too)."""
    PriceSchedule.objects.filter(season=schedule.season, is_active=True).exclude(pk=schedule.pk).update(is_active=False)
    schedule.is_active = True
    schedule.save(update_fields=["is_active"])
    return schedule
