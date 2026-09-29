from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import error_body


class StatusView(APIView):
    """Liveness probe used by the autograder and load balancers."""

    @extend_schema(
        responses=inline_serializer(
            "Status",
            {
                "status": serializers.CharField(),
                "service": serializers.CharField(),
                "time": serializers.DateTimeField(),
            },
        )
    )
    def get(self, request: Request) -> Response:
        return Response({"status": "ok", "service": "kawa-api", "time": timezone.now()})


def not_found(request: HttpRequest, exception: Exception) -> JsonResponse:
    return JsonResponse(error_body("not_found", "Not found."), status=404)


def server_error(request: HttpRequest) -> JsonResponse:
    return JsonResponse(error_body("server_error", "An unexpected error occurred."), status=500)
