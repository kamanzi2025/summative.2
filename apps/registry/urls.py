from rest_framework.routers import SimpleRouter

from .views import FarmerViewSet, PlotViewSet, WashingStationViewSet

router = SimpleRouter(trailing_slash=True)
router.register("farmers", FarmerViewSet, basename="farmer")
router.register("plots", PlotViewSet, basename="plot")
router.register("stations", WashingStationViewSet, basename="station")

urlpatterns = router.urls
