import django_filters

from .models import Plot, RiskStatus


class PlotFilter(django_filters.FilterSet):
    farmer = django_filters.NumberFilter(field_name="farmer_id")
    sector = django_filters.CharFilter(field_name="sector__name", lookup_expr="iexact")
    washing_station = django_filters.CharFilter(field_name="washing_station__name", lookup_expr="iexact")
    risk_status = django_filters.ChoiceFilter(choices=RiskStatus.choices)

    class Meta:
        model = Plot
        fields = ["farmer", "sector", "washing_station", "risk_status"]
