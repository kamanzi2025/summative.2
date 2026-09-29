from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, mixins, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.core.idempotency import NaturalKeyReplayMixin
from apps.core.pagination import DeliveryFeedPagination
from apps.registry.models import WashingStation

from . import services
from .filters import DeliveryFeedFilter
from .models import Delivery
from .serializers import DeliveryFeedSerializer, DeliverySerializer


class DeliveryViewSet(
    NaturalKeyReplayMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Record deliveries (idempotent on `client_reference`) and read the cursor-paginated feed."""

    pagination_class = DeliveryFeedPagination
    filterset_class = DeliveryFeedFilter
    natural_key_field = "client_reference"

    def get_queryset(self) -> QuerySet[Delivery]:
        return services.feed_queryset()

    def get_serializer_class(self) -> type[BaseSerializer]:
        return DeliveryFeedSerializer if self.action == "list" else DeliverySerializer

    def find_replay(self, data: dict[str, Any]) -> Delivery | None:
        return services.find_replay(data.get("washing_station"), data.get("client_reference"))

    def replay_mismatches(self, existing: Delivery, data: dict[str, Any]) -> list[str]:  # type: ignore[override]
        return services.replay_mismatches(existing, data)

    @extend_schema(
        responses={
            201: DeliverySerializer,
            200: OpenApiResponse(DeliverySerializer, description="Replay: this client_reference was already recorded."),
            409: OpenApiResponse(description="client_reference reused with a different body."),
        }
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().create(request, *args, **kwargs)

    def create_new(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # Pricing and the risk snapshot live in the service, so this does not use perform_create.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delivery, created = services.record_delivery(**serializer.validated_data)
        return self.replay_response(delivery, created=created)


class StationDeliveryFeedView(generics.ListAPIView):
    """Emmanuel's station feed: newest deliveries first, cursor-paginated."""

    serializer_class = DeliveryFeedSerializer
    pagination_class = DeliveryFeedPagination
    filterset_class = DeliveryFeedFilter

    def get_queryset(self) -> QuerySet[Delivery]:
        if getattr(self, "swagger_fake_view", False):  # schema generation has no URL kwargs
            return Delivery.objects.none()
        station = get_object_or_404(WashingStation, pk=self.kwargs["station_id"])
        return services.feed_queryset().filter(washing_station=station)
