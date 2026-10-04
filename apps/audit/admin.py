from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only: the trail can be inspected in the admin but not changed or pruned there."""

    list_display = ["occurred_at", "username", "role", "method", "path", "status_code", "coordinate_precision"]
    list_filter = ["role", "resource", "status_code"]
    search_fields = ["username", "path"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
