from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.idempotency import NaturalKeyReplayMixin

from . import services
from .filters import PlotFilter
from .models import Farmer, Plot, WashingStation
from .serializers import FarmerSerializer, PlotSerializer, RiskCheckAttemptSerializer, WashingStationSerializer


def _replay_responses(serializer: type) -> dict[int, Any]:
    return {
        201: serializer,
        200: OpenApiResponse(serializer, description="Identical resend: the existing record is returned."),
        409: OpenApiResponse(description="Natural key already registered with different details."),
    }


@extend_schema(methods=["POST"], responses=_replay_responses(FarmerSerializer))
class FarmerViewSet(
    NaturalKeyReplayMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Registering the same member_number again with identical details replays (200)."""

    queryset = Farmer.objects.select_related("home_station")
    serializer_class = FarmerSerializer
    natural_key_field = "member_number"

    def find_replay(self, data: dict[str, Any]) -> Farmer | None:
        return services.find_farmer_replay(data)

    def replay_mismatches(self, existing: Farmer, data: dict[str, Any]) -> list[str]:  # type: ignore[override]
        return services.farmer_replay_mismatches(existing, data)


@extend_schema(methods=["POST"], responses=_replay_responses(PlotSerializer))
class PlotViewSet(
    NaturalKeyReplayMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Registering a plot returns 201 immediately with `risk_status: "pending"`; the
    deforestation-risk check runs in the background (see apps/registry/tasks.py). Resending the
    same plot_code with identical details replays (200) and does not queue a second check."""

    serializer_class = PlotSerializer
    filterset_class = PlotFilter
    natural_key_field = "plot_code"

    def find_replay(self, data: dict[str, Any]) -> Plot | None:
        return services.find_plot_replay(data)

    def replay_mismatches(self, existing: Plot, data: dict[str, Any]) -> list[str]:  # type: ignore[override]
        return services.plot_replay_mismatches(existing, data)

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
