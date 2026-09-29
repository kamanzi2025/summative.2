"""Recording cherry deliveries at the scale."""

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from apps.pricing.models import PriceEntry
from apps.registry.models import Plot, WashingStation

from .models import Delivery

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")


def feed_queryset() -> QuerySet[Delivery]:
    # One JOINed query per page: the feed serializer reads plot, farmer and station names.
    return Delivery.objects.select_related("plot__farmer", "washing_station").order_by("-recorded_at", "-id")


def find_replay(washing_station: Any, client_reference: Any) -> Delivery | None:
    """Return the delivery a phone already recorded under this idempotency key, if any."""
    if not client_reference or not isinstance(client_reference, str) or not isinstance(washing_station, str):
        return None
    return (
        feed_queryset()
        .filter(washing_station__name__iexact=washing_station.strip(), client_reference=client_reference.strip())
        .first()
    )


def record_delivery(
    *,
    plot: Plot,
    washing_station: WashingStation,
    weight_kg: Decimal,
    grade: str,
    price_entry: PriceEntry,
    delivered_on: date | None = None,
    client_reference: str | None = None,
) -> tuple[Delivery, bool]:
    """Create a delivery, snapshotting today's price and the plot's current risk status.

    Deliveries are accepted whatever the plot's risk status: the farmer is paid the same day,
    and export eligibility is decided later from the plot's status (see ADR.md).
    Returns (delivery, created); created is False when the idempotency key was already used.
    """
    unit_price = price_entry.price_per_kg_rwf
    fields: dict[str, Any] = {
        "plot": plot,
        "washing_station": washing_station,
        "weight_kg": weight_kg,
        "grade": grade,
        "client_reference": client_reference,
        "price_schedule": price_entry.schedule,
        "unit_price_rwf": unit_price,
        "amount_due_rwf": (weight_kg * unit_price).quantize(CENT, rounding=ROUND_HALF_UP),
        "plot_risk_status_at_delivery": plot.risk_status,
    }
    if delivered_on is not None:
        fields["delivered_on"] = delivered_on
    try:
        with transaction.atomic():
            delivery = Delivery.objects.create(**fields)
    except IntegrityError:
        # Two retries of the same phone request raced past find_replay(); return the winner.
        existing = find_replay(washing_station.name, client_reference)
        if existing is None:
            raise
        return existing, False
    logger.info(
        "delivery.recorded",
        extra={
            "delivery_id": delivery.pk,
            "plot_id": plot.pk,
            "station": washing_station.code,
            "risk_status": plot.risk_status,
        },
    )
    return delivery, True
