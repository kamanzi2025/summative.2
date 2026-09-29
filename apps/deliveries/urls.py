from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import DeliveryViewSet, StationDeliveryFeedView

router = SimpleRouter(trailing_slash=True)
router.register("deliveries", DeliveryViewSet, basename="delivery")

urlpatterns = [
    path(
        "stations/<int:station_id>/deliveries/",
        StationDeliveryFeedView.as_view(),
        name="station-delivery-feed",
    ),
    *router.urls,
]
