"""Field-level rules from ROLE_POLICIES: what each role sees *inside* a record it may read.

Record scope (which rows) is visible_to(); this module decides which fields and at what precision:

- national ID: last four digits for field agents; the field is removed for everyone else
- plot coordinates: full stored precision, or the sector's reference point for exporters
- commercial terms (unit_price_rwf, amount_due_rwf): removed for auditors

The rules live in the field classes, so they apply wherever the field appears, including a plot
or farmer nested inside another response (a nested serializer shares its parent's context).
`PolicyFieldsMixin` must be on every serializer that declares one of these fields; it removes the
hidden ones in get_fields().
"""

from typing import Any

from rest_framework import serializers

from .policies import (
    CoordinatePrecision,
    NationalIdVisibility,
    RecordScope,
    RolePolicy,
    policy_for,
)

# Used when a serializer has no request (or the user has no policy): reveal the least. Views
# already refuse such users, so this only guards serializers used outside a request.
MOST_RESTRICTIVE = RolePolicy(
    grants={},
    record_scope=RecordScope.OWN_STATION,
    coordinates=CoordinatePrecision.SECTOR,
    national_id=NationalIdVisibility.HIDDEN,
    commercial_terms=False,
)

NATIONAL_ID_MASK = "*"


def policy_from_context(context: dict[str, Any]) -> RolePolicy:
    request = context.get("request")
    policy = policy_for(request.user) if request is not None else None
    return policy or MOST_RESTRICTIVE


def is_schema_generation(context: dict[str, Any]) -> bool:
    """drf-spectacular builds serializers with a fake view; the published schema shows every field."""
    return getattr(context.get("view"), "swagger_fake_view", False)


def mask_national_id(value: str) -> str:
    return NATIONAL_ID_MASK * (len(value) - 4) + value[-4:]


class NationalIdField(serializers.CharField):
    """Writable as usual. Read back as `************6789` for field agents; removed for other roles."""

    def hidden_for(self, policy: RolePolicy) -> bool:
        return policy.national_id == NationalIdVisibility.HIDDEN

    def to_representation(self, value: Any) -> str:
        # Always masked: LAST_FOUR is the only policy under which the field is present at all.
        return mask_national_id(super().to_representation(value))


class CoordinateField(serializers.DecimalField):
    """A plot's latitude or longitude: the stored value, or its sector's reference point when the
    reader's policy is sector precision. The point is the same for every plot in the sector, so
    it reveals the sector and nothing finer (see DECISION_LOG.md). Writes take the real value."""

    def __init__(self, *, axis: str, **kwargs: Any) -> None:
        if axis not in ("latitude", "longitude"):
            raise ValueError(f"axis must be latitude or longitude, not {axis!r}")
        self.axis = axis
        super().__init__(max_digits=9, decimal_places=6, coerce_to_string=True, **kwargs)

    def get_attribute(self, instance: Any) -> Any:
        if policy_from_context(self.context).coordinates == CoordinatePrecision.SECTOR:
            return getattr(instance.sector, f"centroid_{self.axis}")
        return super().get_attribute(instance)


class CommercialTermField(serializers.DecimalField):
    """Price paid to the farmer; removed for roles without commercial terms (the auditor)."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)

    def hidden_for(self, policy: RolePolicy) -> bool:
        return not policy.commercial_terms


# Removes every field whose `hidden_for(policy)` is true for the requesting user. A comment, not a
# docstring, so serializers without their own docstring do not publish it in schema.yml.
class PolicyFieldsMixin:
    def get_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = super().get_fields()  # type: ignore[misc]
        context = self.context  # type: ignore[attr-defined]
        if is_schema_generation(context):
            return fields
        policy = policy_from_context(context)
        return {
            name: field
            for name, field in fields.items()
            if not (hasattr(field, "hidden_for") and field.hidden_for(policy))
        }
