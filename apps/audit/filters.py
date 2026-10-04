import django_filters

from apps.accounts.policies import CoordinatePrecision, NationalIdVisibility

from .models import AuditLog


class AuditLogFilter(django_filters.FilterSet):
    username = django_filters.CharFilter()
    role = django_filters.CharFilter()
    resource = django_filters.CharFilter()
    status_code = django_filters.NumberFilter()
    # "Who saw exact coordinates?" is ?resource=plots&coordinate_precision=full
    coordinate_precision = django_filters.ChoiceFilter(choices=[(p.value, p.value) for p in CoordinatePrecision])
    # "Who saw farmer identity data?" is ?resource=farmers&national_id=last_four
    national_id = django_filters.ChoiceFilter(choices=[(v.value, v.value) for v in NationalIdVisibility])
    occurred_after = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    occurred_before = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="lt")

    class Meta:
        model = AuditLog
        fields = [
            "username",
            "role",
            "resource",
            "status_code",
            "coordinate_precision",
            "national_id",
            "occurred_after",
            "occurred_before",
        ]
