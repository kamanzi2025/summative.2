from datetime import timedelta

import django_filters
from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils import timezone

from .models import Plot, RiskStatus


def manual_review_q() -> Q:
    """Plots whose check has stayed unverified past the policy window (ADR-001)."""
    cutoff = timezone.now() - timedelta(days=settings.RISK_CHECK_MANUAL_REVIEW_DAYS)
    return Q(risk_status=RiskStatus.UNVERIFIED, created_at__lte=cutoff)


class PlotFilter(django_filters.FilterSet):
    farmer = django_filters.NumberFilter(field_name="farmer_id")
    sector = django_filters.CharFilter(field_name="sector__name", lookup_expr="iexact")
    washing_station = django_filters.CharFilter(field_name="washing_station__name", lookup_expr="iexact")
    risk_status = django_filters.ChoiceFilter(choices=RiskStatus.choices)
    # The compliance review queue: ?requires_manual_review=true
    requires_manual_review = django_filters.BooleanFilter(method="filter_requires_manual_review")

    class Meta:
        model = Plot
        fields = ["farmer", "sector", "washing_station", "risk_status", "requires_manual_review"]

    def filter_requires_manual_review(self, queryset: QuerySet[Plot], name: str, value: bool) -> QuerySet[Plot]:
        return queryset.filter(manual_review_q()) if value else queryset.exclude(manual_review_q())
