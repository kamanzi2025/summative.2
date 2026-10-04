from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone


class AppendOnlyError(Exception):
    """Raised on any attempt to change or remove an audit row."""


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs: Any) -> int:
        raise AppendOnlyError("Audit log rows cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise AppendOnlyError("Audit log rows cannot be deleted.")


class AuditLog(models.Model):
    """One row per request to a protected endpoint: who asked for what, and what they were shown.

    Append-only. Records identifiers and the field rules applied, never the data itself: no
    coordinates, national IDs, prices, request bodies or query strings.
    """

    occurred_at = models.DateTimeField(default=timezone.now, editable=False)
    # SET_NULL keeps the trail if an account is removed; `username` keeps who it was.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    username = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=32, blank=True)
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=255)
    endpoint = models.CharField(max_length=100, blank=True)
    status_code = models.PositiveSmallIntegerField()
    resource = models.CharField(max_length=32)
    object_ids = models.JSONField(default=list)
    # The field rules in force for this response (blank when the user had no policy).
    coordinate_precision = models.CharField(max_length=16, blank=True)
    national_id = models.CharField(max_length=16, blank=True)
    commercial_terms = models.BooleanField(null=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["-occurred_at", "-id"], name="audit_cursor_idx"),
            models.Index(fields=["username", "-occurred_at"], name="audit_user_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.occurred_at:%Y-%m-%d %H:%M:%S} {self.username or 'anonymous'} {self.method} {self.path}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise AppendOnlyError("Audit log rows cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise AppendOnlyError("Audit log rows cannot be deleted.")
