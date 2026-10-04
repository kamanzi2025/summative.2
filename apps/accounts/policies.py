"""Central role policies: the one place that says what each role may do.

Deny by default. Anything not granted here is refused: anonymous or inactive users, a role with
no policy, a field agent with no station, and any resource or action a policy does not list.
Views, querysets and serializers ask this module; they never test role names themselves.

A logged-in user who has no role profile at all gets NO_ROLE_POLICY: the F1 operations (register
farmers, plots and deliveries) under the most restrictive field rules (see DECISION_LOG.md).

The roles are not a ladder. The auditor sees *more* location detail than the exporter partner and
*less* commercial detail, so each policy is a set of independent switches.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser

from .models import Role, UserProfile


class Resource(StrEnum):
    FARMERS = "farmers"
    PLOTS = "plots"
    DELIVERIES = "deliveries"
    STATIONS = "stations"
    AUDIT_LOG = "audit_log"


class Action(StrEnum):
    READ = "read"
    WRITE = "write"


class RecordScope(StrEnum):
    OWN_STATION = "own_station"
    ALL = "all"


class CoordinatePrecision(StrEnum):
    FULL = "full"
    # Every plot in a sector reports the sector's reference point, not a rounding of its own.
    SECTOR = "sector"


class NationalIdVisibility(StrEnum):
    LAST_FOUR = "last_four"
    # The field is dropped from the response entirely, masked form included.
    HIDDEN = "hidden"


AnyUser = AbstractBaseUser | AnonymousUser | None

READ_ONLY = frozenset({Action.READ})
READ_WRITE = frozenset({Action.READ, Action.WRITE})


@dataclass(frozen=True)
class RolePolicy:
    grants: Mapping[Resource, frozenset[Action]]
    record_scope: RecordScope
    coordinates: CoordinatePrecision
    national_id: NationalIdVisibility
    # unit_price_rwf and amount_due_rwf on deliveries.
    commercial_terms: bool

    def __post_init__(self) -> None:
        # Freeze the grants too, so no caller can widen a policy at runtime.
        object.__setattr__(self, "grants", MappingProxyType(dict(self.grants)))

    def allows(self, resource: Resource, action: Action) -> bool:
        return action in self.grants.get(resource, frozenset())


ROLE_POLICIES: Mapping[str, RolePolicy] = MappingProxyType(
    {
        Role.FIELD_AGENT: RolePolicy(
            grants={
                Resource.FARMERS: READ_WRITE,
                Resource.PLOTS: READ_WRITE,
                Resource.DELIVERIES: READ_WRITE,
                Resource.STATIONS: READ_ONLY,
            },
            record_scope=RecordScope.OWN_STATION,
            coordinates=CoordinatePrecision.FULL,
            national_id=NationalIdVisibility.LAST_FOUR,
            commercial_terms=True,
        ),
        Role.EXPORTER_PARTNER: RolePolicy(
            grants={
                Resource.FARMERS: READ_ONLY,
                Resource.PLOTS: READ_ONLY,
                Resource.DELIVERIES: READ_ONLY,
                Resource.STATIONS: READ_ONLY,
            },
            record_scope=RecordScope.ALL,
            coordinates=CoordinatePrecision.SECTOR,
            national_id=NationalIdVisibility.HIDDEN,
            commercial_terms=True,
        ),
        Role.COMPLIANCE_AUDITOR: RolePolicy(
            grants={
                Resource.FARMERS: READ_ONLY,
                Resource.PLOTS: READ_ONLY,
                Resource.DELIVERIES: READ_ONLY,
                Resource.STATIONS: READ_ONLY,
                Resource.AUDIT_LOG: READ_ONLY,
            },
            record_scope=RecordScope.ALL,
            coordinates=CoordinatePrecision.FULL,
            national_id=NationalIdVisibility.HIDDEN,
            commercial_terms=False,
        ),
    }
)


# Logged in, active, but never given a role. Keeps the F1 operations working (register and list
# farmers, plots and deliveries) while revealing the least: no national ID, sector reference
# points instead of coordinates, no prices, no audit log.
NO_ROLE_POLICY = RolePolicy(
    grants={
        Resource.FARMERS: READ_WRITE,
        Resource.PLOTS: READ_WRITE,
        Resource.DELIVERIES: READ_WRITE,
        Resource.STATIONS: READ_ONLY,
    },
    record_scope=RecordScope.ALL,
    coordinates=CoordinatePrecision.SECTOR,
    national_id=NationalIdVisibility.HIDDEN,
    commercial_terms=False,
)


def profile_for(user: AnyUser) -> UserProfile | None:
    """The user's profile, or None when they must be treated as having no role."""
    if user is None or not user.is_authenticated or not user.is_active:
        return None
    # Missing reverse one-to-one raises RelatedObjectDoesNotExist, an AttributeError subclass.
    profile: UserProfile | None = getattr(user, "profile", None)
    if profile is None:
        return None
    if profile.role == Role.FIELD_AGENT and profile.washing_station_id is None:
        return None
    return profile


def policy_for(user: AnyUser) -> RolePolicy | None:
    """The user's policy, or None (deny everything)."""
    if user is None or not user.is_authenticated or not user.is_active:
        return None
    if getattr(user, "profile", None) is None:
        return NO_ROLE_POLICY
    # A profile that exists but is invalid (unknown role, field agent without a station) is denied.
    profile = profile_for(user)
    return ROLE_POLICIES.get(profile.role) if profile else None


def can(user: AnyUser, resource: Resource, action: Action) -> bool:
    policy = policy_for(user)
    return policy is not None and policy.allows(resource, action)


def scoped_station_id(user: AnyUser) -> int | None:
    """The station a station-scoped user is bound to; None for everyone else."""
    policy = policy_for(user)
    if policy is None or policy.record_scope != RecordScope.OWN_STATION:
        return None
    profile = profile_for(user)
    return profile.washing_station_id if profile else None
