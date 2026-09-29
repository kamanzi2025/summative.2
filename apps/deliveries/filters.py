import django_filters
from django.db.models import QuerySet

from apps.pricing.models import Grade
from apps.registry.models import RiskStatus

from .models import Delivery


class DeliveryFeedFilter(django_filters.FilterSet):
    washing_station = django_filters.CharFilter(field_name="washing_station__name", lookup_expr="iexact")
    grade = django_filters.ChoiceFilter(choices=Grade.choices)
    # Current plot status, i.e. what decides export eligibility today.
    risk_status = django_filters.ChoiceFilter(field_name="plot__risk_status", choices=RiskStatus.choices)
    # Phones pass the recorded_at of the newest row they hold to fetch only newer rows.
    since = django_filters.IsoDateTimeFilter(field_name="recorded_at", lookup_expr="gt")
    # ?exportable=false&risk_status=flagged is the review list for cherry already paid for.
    exportable = django_filters.BooleanFilter(method="filter_exportable")

    class Meta:
        model = Delivery
        fields = ["washing_station", "grade", "risk_status", "since", "exportable"]

    def filter_exportable(self, queryset: QuerySet[Delivery], name: str, value: bool) -> QuerySet[Delivery]:
        clear = {"plot__risk_status": RiskStatus.CLEAR}
        return queryset.filter(**clear) if value else queryset.exclude(**clear)
