from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.accounts.scoping import StationScopedQuerySet
from apps.pricing.models import Grade, PriceSchedule
from apps.registry.models import Plot, RiskStatus, WashingStation

# Upper bound for one farmer's delivery at the scale; larger values are data-entry errors.
MAX_DELIVERY_WEIGHT_KG = 500


class DeliveryQuerySet(StationScopedQuerySet):
    def own_station_q(self, station_id: int) -> Q:
        return Q(washing_station_id=station_id)


class Delivery(models.Model):
    """Cherry weighed in at a washing station.

    A delivery references the *plot* (not the farmer) so every export lot traces back to land.
    Price and plot risk status are snapshotted when the delivery is recorded, so a later price
    change or risk verdict never rewrites what the farmer was paid or what was known at the time.
    """

    plot = models.ForeignKey(Plot, on_delete=models.PROTECT, related_name="deliveries")
    washing_station = models.ForeignKey(WashingStation, on_delete=models.PROTECT, related_name="deliveries")
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2)
    grade = models.CharField(max_length=1, choices=Grade.choices)
    delivered_on = models.DateField(default=timezone.localdate)
    # Idempotency key generated on the phone; lets 2G retries replay safely.
    # NULL (not "") when absent, so the per-station unique constraint ignores it.
    client_reference = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001

    price_schedule = models.ForeignKey(PriceSchedule, on_delete=models.PROTECT, related_name="deliveries")
    unit_price_rwf = models.DecimalField(max_digits=10, decimal_places=2)
    amount_due_rwf = models.DecimalField(max_digits=12, decimal_places=2)
    plot_risk_status_at_delivery = models.CharField(max_length=12, choices=RiskStatus.choices)
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = DeliveryQuerySet.as_manager()

    class Meta:
        ordering = ["-recorded_at", "-id"]
        verbose_name_plural = "deliveries"
        indexes = [
            # The station feed: WHERE washing_station = ? ORDER BY recorded_at DESC, id DESC.
            models.Index(fields=["washing_station", "-recorded_at", "-id"], name="delivery_station_feed_idx"),
            models.Index(fields=["-recorded_at", "-id"], name="delivery_feed_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["washing_station", "client_reference"],
                condition=Q(client_reference__isnull=False),
                name="unique_client_reference_per_station",
            ),
            models.CheckConstraint(
                condition=Q(weight_kg__gt=0) & Q(weight_kg__lte=MAX_DELIVERY_WEIGHT_KG),
                name="delivery_weight_in_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.weight_kg} kg {self.grade} from {self.plot_id} at {self.washing_station_id}"

    @property
    def is_exportable(self) -> bool:
        """Only cherry from plots that are currently clear may enter a traceability export."""
        return self.plot.risk_status == RiskStatus.CLEAR
