from django.conf import settings
from django.utils.cache import patch_cache_control
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import PriceScheduleSerializer
from .services import get_active_schedule


class PriceScheduleView(APIView):
    """Active season's per-grade farm-gate prices.

    Not cached on the server: every request reads the database, so a price change is visible to
    the next request. Clients may reuse a response for PRICE_SCHEDULE_MAX_AGE_SECONDS (default
    60 s), which is the whole staleness window.
    """

    @extend_schema(responses=PriceScheduleSerializer)
    def get(self, request: Request) -> Response:
        schedule = get_active_schedule()
        if schedule is None:
            raise NotFound("No active price schedule.")
        response = Response(PriceScheduleSerializer(schedule).data)
        patch_cache_control(response, public=True, max_age=settings.PRICE_SCHEDULE_MAX_AGE_SECONDS)
        return response
