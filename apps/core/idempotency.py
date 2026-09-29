"""Idempotent POST for resources that have a natural key.

Station phones on 2G often resend a request whose response they never received. An identical
resend returns the existing record with 200 instead of a duplicate; the same key with different
details is a genuine conflict (409). Farmers replay on `member_number`, plots on `plot_code`, and
deliveries on `client_reference` (per station). All three share this one implementation.
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

    def replay_response(self, instance: Model, *, created: bool) -> Response:
        serializer = self.get_serializer(instance)  # type: ignore[attr-defined]
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            headers={"Idempotent-Replayed": "false" if created else "true"},
        )

    def create_new(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create path when no replay matched. Override when creation needs a service call."""
        response: Response = super().create(request, *args, **kwargs)  # type: ignore[misc]
        response["Idempotent-Replayed"] = "false"
        return response

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        existing = self.find_replay(data)
        if existing is None:
            return self.create_new(request, *args, **kwargs)
        mismatched = self.replay_mismatches(existing, data)
        if mismatched:
            key = str(data.get(self.natural_key_field, "")).strip()
            raise Conflict(
                f"{self.natural_key_field} {key!r} was already used for record {existing.pk} with different details.",
                details={"id": existing.pk, "mismatched_fields": mismatched},
            )
        return self.replay_response(existing, created=False)
