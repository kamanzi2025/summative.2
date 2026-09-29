from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from .filters import PlotFilter
from .models import Farmer, Plot, WashingStation
from .serializers import FarmerSerializer, PlotSerializer, RiskCheckAttemptSerializer, WashingStationSerializer


class FarmerViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Farmer.objects.select_related("home_station")
    serializer_class = FarmerSerializer


class PlotViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Registering a plot returns 201 immediately with `risk_status: "pending"`; the
    deforestation-risk check runs in the background (see apps/registry/tasks.py)."""

    serializer_class = PlotSerializer
    filterset_class = PlotFilter

    def get_queryset(self) -> QuerySet[Plot]:
        return Plot.objects.select_related("sector", "washing_station")

    @extend_schema(responses=RiskCheckAttemptSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="risk-checks", pagination_class=None, filterset_class=None)
    def risk_checks(self, request: Request, pk: str | None = None) -> Response:
        """Every registry call made for this plot, oldest first: evidence of retries."""
        plot = self.get_object()
        attempts = plot.risk_checks.order_by("attempt_number")
        return Response(RiskCheckAttemptSerializer(attempts, many=True).data)


class WashingStationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WashingStation.objects.select_related("sector")
    serializer_class = WashingStationSerializer
    pagination_class = None
