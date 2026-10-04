import django_filters

from .models import AuditLog


class AuditLogFilter(django_filters.FilterSet):
    username = django_filters.CharFilter()
    role = django_filters.CharFilter()
    resource = django_filters.CharFilter()
    status_code = django_filters.NumberFilter()
    occurred_after = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    occurred_before = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="lt")

    class Meta:
        model = AuditLog
        fields = ["username", "role", "resource", "status_code", "occurred_after", "occurred_before"]
