from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.registry.services import risk_check_backlog

from .exceptions import error_body


class StatusView(APIView):
    """Database-dependent API status response with a risk-check backlog snapshot.

    The handler reads the database through `risk_check_backlog()`. `status` stays "ok" when the
    API and that database query work, even if the registry, broker, or worker is unavailable.
    `risk_checks.healthy` only reflects whether plots have become stale; it is not a Redis or
    Celery worker ping and is not a complete readiness signal. Public, so a monitor can call it
    without credentials.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer(
            "Status",
            {
                "status": serializers.CharField(),
                "service": serializers.CharField(),
                "time": serializers.DateTimeField(),
                "risk_checks": inline_serializer(
                    "RiskCheckBacklog",
                    {
                        "pending": serializers.IntegerField(),
                        "unverified": serializers.IntegerField(),
                        "stale": serializers.IntegerField(),
                        "requires_manual_review": serializers.IntegerField(),
                        "last_attempt_at": serializers.DateTimeField(allow_null=True),
                        "healthy": serializers.BooleanField(),
                    },
                ),
            },
        )
    )
    def get(self, request: Request) -> Response:
        return Response(
            {"status": "ok", "service": "kawa-api", "time": timezone.now(), "risk_checks": risk_check_backlog()}
        )


def not_found(request: HttpRequest, exception: Exception) -> JsonResponse:
    return JsonResponse(error_body("not_found", "Not found."), status=404)


def server_error(request: HttpRequest) -> JsonResponse:
    return JsonResponse(error_body("server_error", "An unexpected error occurred."), status=500)
