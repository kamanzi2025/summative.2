from django.conf import settings
from django.db import models
from django.db.models import Q


class Role(models.TextChoices):
    """The F2 roles. What each one may do lives in apps/accounts/policies.py, not here."""

    FIELD_AGENT = "field_agent", "Field agent"
    EXPORTER_PARTNER = "exporter_partner", "Exporter partner"
    COMPLIANCE_AUDITOR = "compliance_auditor", "Compliance auditor"


class UserProfile(models.Model):
    """One role per staff user. A user without a profile has no API access at all."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=32, choices=Role.choices)
    # Field agents are scoped to one station; partners and auditors see every station.
    washing_station = models.ForeignKey(
        "registry.WashingStation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="staff_profiles",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(role__in=Role.values), name="profile_role_known"),
            # A field agent without a station would have no scope; anyone else with one would
            # suggest a scope that the policy does not apply.
            models.CheckConstraint(
                condition=(Q(role=Role.FIELD_AGENT) & Q(washing_station__isnull=False))
                | (~Q(role=Role.FIELD_AGENT) & Q(washing_station__isnull=True)),
                name="profile_station_iff_field_agent",
            ),
        ]

    def __str__(self) -> str:
        station = f" @ {self.washing_station}" if self.washing_station_id else ""
        return f"{self.user} ({self.role}{station})"
