from rest_framework import generics

from apps.accounts.policies import Resource
from apps.core.pagination import CreatedAtCursorPagination

from .filters import AuditLogFilter
from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogPagination(CreatedAtCursorPagination):
    ordering = ("-occurred_at", "-id")


class AuditLogListView(generics.ListAPIView):
    """Who accessed farmer, plot and delivery data, newest first. Compliance auditors only.
    Reading this list is itself recorded."""

    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    pagination_class = AuditLogPagination
    filterset_class = AuditLogFilter
    policy_resource = Resource.AUDIT_LOG
