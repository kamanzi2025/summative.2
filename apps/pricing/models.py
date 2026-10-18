from django.db import models
from django.db.models import Q
from django.utils import timezone


class Grade(models.TextChoices):
    """Cherry grade assigned at the scale."""

    A = "A", "Grade A (ripe red cherry)"
    B = "B", "Grade B (mixed ripeness)"
    C = "C", "Grade C (floaters / under-ripe)"


class PriceSchedule(models.Model):
    """Prices for one season; active schedules may be future-dated and take effect by date."""

    season = models.CharField(max_length=10, help_text='e.g. "2026A"')
    effective_from = models.DateField()
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-effective_from", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["effective_from"],
                condition=Q(is_active=True),
                name="one_active_schedule_per_effective_date",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.season} from {self.effective_from}{' (active)' if self.is_active else ''}"


class PriceEntry(models.Model):
    schedule = models.ForeignKey(PriceSchedule, on_delete=models.CASCADE, related_name="entries")
    grade = models.CharField(max_length=1, choices=Grade.choices)
    price_per_kg_rwf = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["grade"]
        constraints = [
            models.UniqueConstraint(fields=["schedule", "grade"], name="one_price_per_grade_per_schedule"),
            models.CheckConstraint(condition=Q(price_per_kg_rwf__gt=0), name="price_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.grade}: {self.price_per_kg_rwf} RWF/kg"
