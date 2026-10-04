import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.db import IntegrityError, transaction

from apps.accounts.models import Role, UserProfile
from apps.accounts.policies import (
    ANONYMOUS_POLICY,
    NO_ROLE_POLICY,
    ROLE_POLICIES,
    Action,
    CoordinatePrecision,
    NationalIdVisibility,
    RecordScope,
    Resource,
    can,
    policy_for,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def make_staff(nyaruguru):
    def _make(role, *, station=None, username=None, **user_fields):
        user = User.objects.create_user(username=username or f"{role}_user", password="x", **user_fields)
        if role == Role.FIELD_AGENT and station is None:
            station = nyaruguru
        UserProfile.objects.create(user=user, role=role, washing_station=station)
        return User.objects.get(pk=user.pk)

    return _make


def test_every_role_has_a_policy():
    assert set(ROLE_POLICIES) == set(Role.values)


@pytest.mark.parametrize("resource", list(Resource))
def test_anonymous_callers_can_read_nothing(resource):
    assert policy_for(AnonymousUser()) is ANONYMOUS_POLICY
    assert not can(AnonymousUser(), resource, Action.READ)


def test_anonymous_callers_may_only_register_farmers_plots_and_deliveries():
    writable = {r for r in Resource if can(AnonymousUser(), r, Action.WRITE)}
    assert writable == {Resource.FARMERS, Resource.PLOTS, Resource.DELIVERIES}
    assert (ANONYMOUS_POLICY.coordinates, ANONYMOUS_POLICY.national_id, ANONYMOUS_POLICY.commercial_terms) == (
        CoordinatePrecision.SECTOR,
        NationalIdVisibility.HIDDEN,
        False,
    )


@pytest.mark.parametrize("resource", list(Resource))
@pytest.mark.parametrize("action", list(Action))
def test_no_user_at_all_is_denied_everything(resource, action):
    assert policy_for(None) is None
    assert not can(None, resource, action)


@pytest.mark.parametrize("make_user", [User.objects.create_user, User.objects.create_superuser])
def test_logged_in_user_without_a_role_gets_the_most_restrictive_f1_policy(make_user):
    user = make_user(username="no_role", password="x")
    assert policy_for(user) is NO_ROLE_POLICY
    # The F1 operations still work...
    for resource in (Resource.FARMERS, Resource.PLOTS, Resource.DELIVERIES):
        assert can(user, resource, Action.READ) and can(user, resource, Action.WRITE)
    # ...but nothing sensitive is revealed, and the audit log stays closed.
    assert not can(user, Resource.AUDIT_LOG, Action.READ)
    assert not can(user, Resource.STATIONS, Action.WRITE)
    assert (NO_ROLE_POLICY.coordinates, NO_ROLE_POLICY.national_id, NO_ROLE_POLICY.commercial_terms) == (
        CoordinatePrecision.SECTOR,
        NationalIdVisibility.HIDDEN,
        False,
    )


def test_inactive_user_without_a_role_is_still_denied():
    user = User.objects.create_user(username="gone", password="x", is_active=False)
    assert policy_for(user) is None


def test_inactive_user_is_denied_even_with_a_role(make_staff):
    user = make_staff(Role.COMPLIANCE_AUDITOR, is_active=False)
    assert policy_for(user) is None


@pytest.mark.parametrize("role", [Role.EXPORTER_PARTNER, Role.COMPLIANCE_AUDITOR])
def test_partner_and_auditor_are_read_only(make_staff, role):
    user = make_staff(role)
    for resource in Resource:
        assert not can(user, resource, Action.WRITE)
    assert can(user, Resource.PLOTS, Action.READ)


def test_field_agent_reads_and_writes_station_records_but_not_the_audit_log(make_staff):
    agent = make_staff(Role.FIELD_AGENT)
    for resource in (Resource.FARMERS, Resource.PLOTS, Resource.DELIVERIES):
        assert can(agent, resource, Action.READ)
        assert can(agent, resource, Action.WRITE)
    assert not can(agent, Resource.STATIONS, Action.WRITE)
    assert not can(agent, Resource.AUDIT_LOG, Action.READ)


def test_only_the_auditor_reads_the_audit_log(make_staff):
    assert can(make_staff(Role.COMPLIANCE_AUDITOR), Resource.AUDIT_LOG, Action.READ)
    assert not can(make_staff(Role.EXPORTER_PARTNER), Resource.AUDIT_LOG, Action.READ)


def test_policies_match_the_f2_access_matrix():
    agent, partner, auditor = (ROLE_POLICIES[r] for r in Role.values)
    assert (agent.record_scope, agent.coordinates, agent.national_id, agent.commercial_terms) == (
        RecordScope.OWN_STATION,
        CoordinatePrecision.FULL,
        NationalIdVisibility.LAST_FOUR,
        True,
    )
    assert (partner.record_scope, partner.coordinates, partner.national_id, partner.commercial_terms) == (
        RecordScope.ALL,
        CoordinatePrecision.SECTOR,
        NationalIdVisibility.HIDDEN,
        True,
    )
    # Not a ladder: the auditor sees finer coordinates than the partner but no commercial terms.
    assert (auditor.record_scope, auditor.coordinates, auditor.national_id, auditor.commercial_terms) == (
        RecordScope.ALL,
        CoordinatePrecision.FULL,
        NationalIdVisibility.HIDDEN,
        False,
    )


def test_policies_cannot_be_widened_at_runtime():
    with pytest.raises(TypeError):
        ROLE_POLICIES[Role.EXPORTER_PARTNER].grants[Resource.AUDIT_LOG] = frozenset({Action.READ})  # type: ignore[index]
    with pytest.raises(TypeError):
        ROLE_POLICIES["superuser"] = ROLE_POLICIES[Role.COMPLIANCE_AUDITOR]  # type: ignore[index]


def test_field_agent_must_have_a_station():
    user = User.objects.create_user(username="agent", password="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        UserProfile.objects.create(user=user, role=Role.FIELD_AGENT, washing_station=None)


@pytest.mark.parametrize("role", [Role.EXPORTER_PARTNER, Role.COMPLIANCE_AUDITOR])
def test_station_is_rejected_for_unscoped_roles(nyaruguru, role):
    user = User.objects.create_user(username="partner", password="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        UserProfile.objects.create(user=user, role=role, washing_station=nyaruguru)


def test_unknown_role_is_rejected_by_the_database():
    user = User.objects.create_user(username="ghost", password="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        UserProfile.objects.create(user=user, role="superuser")
