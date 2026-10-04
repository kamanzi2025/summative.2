from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.accounts.scoping import StationScopedQuerySet

# Rwanda's bounding box, padded. Coordinates outside it are typos, not plots. It is a coarse check:
# the southern edge sits below the real border (~-2.84) so the F2 fixture plot M2 (-2.90) fits.
# Polygon-based border validation is deferred (see DECISION_LOG.md).
RWANDA_LAT_MIN, RWANDA_LAT_MAX = Decimal("-2.95"), Decimal("-1.04")
RWANDA_LON_MIN, RWANDA_LON_MAX = Decimal("28.85"), Decimal("30.90")
MAX_PLOT_AREA_HECTARES = Decimal("50")


class Sector(models.Model):
    """Administrative sector. Exporter partners receive a plot's sector reference point instead of
    the plot's own coordinates, so location precision is keyed to the sector."""

    name = models.CharField(max_length=80, unique=True)
    district = models.CharField(max_length=80)
    # The sector's reference point: what exporters receive instead of a plot's own coordinates,
    # so every plot in the sector reports the same location (see DECISION_LOG.md).
    centroid_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    centroid_longitude = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(centroid_latitude__gte=RWANDA_LAT_MIN, centroid_latitude__lte=RWANDA_LAT_MAX)
                & Q(centroid_longitude__gte=RWANDA_LON_MIN, centroid_longitude__lte=RWANDA_LON_MAX),
                name="sector_centroid_inside_rwanda",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.district})"

    @property
    def reference_point(self) -> tuple[Decimal, Decimal]:
        return self.centroid_latitude, self.centroid_longitude


class WashingStationQuerySet(StationScopedQuerySet):
    def own_station_q(self, station_id: int) -> Q:
        return Q(pk=station_id)


class WashingStation(models.Model):
    name = models.CharField(max_length=80, unique=True)
    code = models.CharField(max_length=16, unique=True)
    sector = models.ForeignKey(Sector, on_delete=models.PROTECT, related_name="washing_stations")

    objects = WashingStationQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class FarmerQuerySet(StationScopedQuerySet):
    def own_station_q(self, station_id: int) -> Q:
        # A station's farmers: anyone with a plot delivering there, plus farmers registered there
        # who have no plot yet. Exists() rather than a join, so a farmer with two plots is one row.
        has_plot_here = Exists(Plot.objects.filter(farmer=OuterRef("pk"), washing_station_id=station_id))
        return has_plot_here | Q(home_station_id=station_id)


class Farmer(models.Model):
    full_name = models.CharField(max_length=150)
    member_number = models.CharField(max_length=32, unique=True)
    cooperative = models.CharField(max_length=120, blank=True)
    # Stored in E.164 (+2507XXXXXXXX); the serializer normalises local 07XXXXXXXX input.
    phone = models.CharField(max_length=13, unique=True)
    national_id = models.CharField(max_length=16, unique=True, null=True, blank=True)
    home_station = models.ForeignKey(
        WashingStation, on_delete=models.PROTECT, null=True, blank=True, related_name="farmers"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = FarmerQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            # Matches the cursor ordering of GET /api/farmers/, so each page is an index range scan.
            models.Index(fields=["-created_at", "-id"], name="farmer_list_cursor_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.member_number})"


class RiskStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CLEAR = "clear", "Clear"
    FLAGGED = "flagged", "Flagged"
    # Registry never answered after all retries. Not a verdict; the sweeper keeps retrying.
    UNVERIFIED = "unverified", "Unverified"


class PlotQuerySet(StationScopedQuerySet):
    def own_station_q(self, station_id: int) -> Q:
        return Q(washing_station_id=station_id)


class Plot(models.Model):
    farmer = models.ForeignKey(Farmer, on_delete=models.PROTECT, related_name="plots")
    plot_code = models.CharField(max_length=32, unique=True)
    label = models.CharField(max_length=100, blank=True)
    # Foreign keys are indexed automatically, which covers Plot(sector) and Plot(washing_station).
    sector = models.ForeignKey(Sector, on_delete=models.PROTECT, related_name="plots")
    washing_station = models.ForeignKey(WashingStation, on_delete=models.PROTECT, related_name="plots")
    area_hectares = models.DecimalField(max_digits=8, decimal_places=4)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    risk_status = models.CharField(max_length=12, choices=RiskStatus.choices, default=RiskStatus.PENDING)
    risk_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = PlotQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            # Serves the risk_status filter and the stale-check sweeper (status + age).
            models.Index(fields=["risk_status", "created_at"], name="plot_risk_status_created_idx"),
            # Matches the cursor ordering of GET /api/plots/, so each page is an index range scan.
            models.Index(fields=["-created_at", "-id"], name="plot_list_cursor_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(area_hectares__gt=0) & Q(area_hectares__lte=MAX_PLOT_AREA_HECTARES),
                name="plot_area_in_range",
            ),
            models.CheckConstraint(
                condition=Q(latitude__gte=RWANDA_LAT_MIN, latitude__lte=RWANDA_LAT_MAX)
                & Q(longitude__gte=RWANDA_LON_MIN, longitude__lte=RWANDA_LON_MAX),
                name="plot_inside_rwanda",
            ),
        ]

    def __str__(self) -> str:
        return self.plot_code

    @property
    def requires_manual_review(self) -> bool:
        """Unverified for longer than the policy window: a person must look at it."""
        if self.risk_status != RiskStatus.UNVERIFIED:
            return False
        window = timedelta(days=settings.RISK_CHECK_MANUAL_REVIEW_DAYS)
        return timezone.now() - self.created_at >= window


class AttemptOutcome(models.TextChoices):
    RUNNING = "running", "Running"
    CLEAR = "clear", "Clear"
    FLAGGED = "flagged", "Flagged"
    ERROR = "error", "Error"
    TIMEOUT = "timeout", "Timeout"


class RiskCheckAttempt(models.Model):
    """One call to the deforestation-risk registry. This table is the audit trail of retries."""

    plot = models.ForeignKey(Plot, on_delete=models.CASCADE, related_name="risk_checks")
    attempt_number = models.PositiveIntegerField()
    task_id = models.CharField(max_length=255, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=10, choices=AttemptOutcome.choices, default=AttemptOutcome.RUNNING)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["plot", "attempt_number"]
        indexes = [models.Index(fields=["plot", "started_at"], name="riskcheck_plot_started_idx")]
        constraints = [
            models.UniqueConstraint(fields=["plot", "attempt_number"], name="unique_attempt_number_per_plot"),
        ]

    def __str__(self) -> str:
        return f"{self.plot_id} #{self.attempt_number}: {self.outcome}"
