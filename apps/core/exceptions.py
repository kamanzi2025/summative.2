"""One error envelope for every API failure.

Shape: {"error": {"code": str, "message": str, "details": dict}}
"""

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class Conflict(exceptions.APIException):
    """The request contradicts existing data: a write that raced past validation into a uniqueness
    constraint, or an idempotency key reused with a different body."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with existing data."
    default_code = "conflict"

    def __init__(self, detail: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.details = details or {}


def error_body(code: str, message: str, details: Any | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def kawa_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    # Duplicates that validation can see are 400s with field details. An IntegrityError only
    # reaches here when two requests raced past validation, so it is reported as a 409.
    if isinstance(exc, IntegrityError):
        logger.warning("api.integrity_conflict", extra={"error": str(exc)})
        exc = Conflict()
    elif isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(as_serializer_error(exc))
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound(str(exc) or None)
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied(str(exc) or None)

    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("api.unhandled_error", exc_info=exc)
        return Response(
            error_body("server_error", "An unexpected error occurred."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        details = response.data if isinstance(response.data, dict) else {"non_field_errors": response.data}
        response.data = error_body("validation_error", "The request data is invalid.", details)
    else:
        detail = response.data.get("detail", "") if isinstance(response.data, dict) else response.data
        code = getattr(exc, "default_code", "error")
        if isinstance(exc, exceptions.APIException):
            codes = exc.get_codes()
            code = codes if isinstance(codes, str) else code
        response.data = error_body(code, str(detail), getattr(exc, "details", None))
    return response
