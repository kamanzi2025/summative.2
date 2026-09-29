"""Idempotent POST for resources that have a natural key (member number, plot code).

Station phones on 2G often resend a registration whose response they never received. An
identical resend returns the existing record with 200 instead of a duplicate-key 400; the same
key with different details is a genuine conflict (409). Deliveries follow the same rule with
their `client_reference` (apps/deliveries/views.py).
"""

from typing import Any

from django.db.models import Model
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from .exceptions import Conflict


class NaturalKeyReplayMixin:
    """Mix into a viewset that has CreateModelMixin. Subclasses define the natural key."""

    natural_key_field: str

    def find_replay(self, data: dict[str, Any]) -> Model | None:
        raise NotImplementedError

    def replay_mismatches(self, existing: Model, data: dict[str, Any]) -> list[str]:
        raise NotImplementedError

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        existing = self.find_replay(data)
        if existing is not None:
            mismatched = self.replay_mismatches(existing, data)
            if mismatched:
                raise Conflict(
                    f"{self.natural_key_field} {data.get(self.natural_key_field)!r} is already registered "
                    "with different details.",
                    details={"id": existing.pk, "mismatched_fields": mismatched},
                )
            serializer = self.get_serializer(existing)  # type: ignore[attr-defined]
            return Response(serializer.data, status=status.HTTP_200_OK, headers={"Idempotent-Replayed": "true"})
        response: Response = super().create(request, *args, **kwargs)  # type: ignore[misc]
        response["Idempotent-Replayed"] = "false"
        return response
