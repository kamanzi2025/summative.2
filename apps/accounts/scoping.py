"""Record scoping: `Model.objects.visible_to(user)` returns only the rows that user's role may see.

Deny by default, like the policies it reads: a user with no policy gets an empty queryset. Every
view, sub-route and replay lookup starts from visible_to(), so a record outside the caller's scope
is a 404 (indistinguishable from one that does not exist), never a 403 that confirms it exists.
"""

from typing import Any, Self

from django.db import models
from django.db.models import Q

from .policies import AnyUser, RecordScope, policy_for, scoped_station_id


class StationScopedQuerySet(models.QuerySet):
    """Subclasses say how a row belongs to a station; the policy says whether that bounds the user."""

    def own_station_q(self, station_id: int) -> Q:
        raise NotImplementedError

    def visible_to(self, user: AnyUser) -> Self:
        policy = policy_for(user)
        if policy is None:
            return self.none()
        if policy.record_scope == RecordScope.ALL:
            return self
        station_id = scoped_station_id(user)
        return self.none() if station_id is None else self.filter(self.own_station_q(station_id))


class ScopedRelationsMixin:
    """For serializers: every related field whose queryset supports visible_to() is narrowed to
    the requesting user, so a write can only point at records they may see. An out-of-scope id or
    name fails validation as "does not exist", the same as one that really does not exist."""

    def get_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = super().get_fields()  # type: ignore[misc]
        request = self.context.get("request")  # type: ignore[attr-defined]
        if request is not None:
            for field in fields.values():
                target = getattr(field, "child_relation", field)
                queryset = getattr(target, "queryset", None)
                # ModelSerializer's auto-built relations hold the model's manager, not a queryset.
                if isinstance(queryset, models.Manager):
                    queryset = queryset.all()
                if isinstance(queryset, StationScopedQuerySet):
                    target.queryset = queryset.visible_to(request.user)
        return fields
