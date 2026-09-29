from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.core.pagination import DeliveryFeedPagination
from apps.registry.models import WashingStation

from . import services
from .filters import DeliveryFeedFilter
from .models import Delivery
from .serializers import DeliveryFeedSerializer, DeliverySerializer


class DeliveryViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Record deliveries (idempotent on `client_reference`) and read the cursor-paginated feed."""

    pagination_class = DeliveryFeedPagination
    filterset_class = DeliveryFeedFilter

    def get_queryset(self) -> QuerySet[Delivery]:
        return services.feed_queryset()

    def get_serializer_class(self) -> type[BaseSerializer]:
        return DeliveryFeedSerializer if self.action == "list" else DeliverySerializer

    @extend_schema(
        responses={
            201: DeliverySerializer,
            200: OpenApiResponse(DeliverySerializer, description="Replay: this client_reference was already recorded."),
        }
    )
    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        replay = services.find_replay(data.get("washing_station"), data.get("client_reference"))
        if replay is not None:
            return self._respond(replay, created=False)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delivery, created = services.record_delivery(**serializer.validated_data)
        return self._respond(delivery, created=created)

    def _respond(self, delivery: Delivery, *, created: bool) -> Response:
        return Response(
            DeliverySerializer(delivery, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            headers={"Idempotent-Replayed": "false" if created else "true"},
        )


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
