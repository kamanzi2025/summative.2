"""AuditLog: one append-only row per request to a protected endpoint, readable by auditors only."""

import json
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import RequestFactory
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.audit.models import AppendOnlyError, AuditLog
from apps.registry.models import Plot, Sector

pytestmark = pytest.mark.django_db

AGENT, EXPORTER, AUDITOR = "field_agent_user", "exporter_user", "auditor_user"


@pytest.fixture(autouse=True)
def seeded(db):
    call_command("seed_rbac_fixtures", stdout=StringIO())


def client_for(username, **kwargs):
    client = APIClient(**kwargs)
    client.force_login(User.objects.get(username=username))
    return client


def only_new_row(action):
    """Run `action` and return the single audit row it wrote."""
    before = set(AuditLog.objects.values_list("pk", flat=True))
    action()
    rows = AuditLog.objects.exclude(pk__in=before)
    assert rows.count() == 1, list(rows.values("method", "path"))
    return rows.get()


def plot_id(code):
    return Plot.objects.get(plot_code=code).pk


# --- What a row records -----------------------------------------------------------------------


def test_field_agent_list_is_recorded_with_the_rules_applied():
    row = only_new_row(lambda: client_for(AGENT).get("/api/plots/"))
    assert (row.username, row.role, row.user.username) == (AGENT, "field_agent", AGENT)
    assert (row.method, row.path, row.endpoint, row.status_code, row.resource) == (
        "GET",
        "/api/plots/",
        "plot-list",
        200,
        "plots",
    )
    assert sorted(row.object_ids) == sorted([plot_id("KWA-SEED-K1"), plot_id("KWA-SEED-K2")])
    assert (row.coordinate_precision, row.national_id, row.commercial_terms) == ("full", "last_four", True)


def test_exporter_row_records_sector_precision():
    row = only_new_row(lambda: client_for(EXPORTER).get("/api/plots/"))
    assert (row.role, row.coordinate_precision, row.national_id) == ("exporter_partner", "sector", "hidden")
    assert len(row.object_ids) == 4


def test_auditor_row_records_that_commercial_terms_were_withheld():
    row = only_new_row(lambda: client_for(AUDITOR).get("/api/deliveries/"))
    assert (row.resource, row.commercial_terms, row.coordinate_precision) == ("deliveries", False, "full")


def test_detail_and_sub_route_record_the_plot_id():
    k1 = plot_id("KWA-SEED-K1")
    client = client_for(AGENT)
    assert only_new_row(lambda: client.get(f"/api/plots/{k1}/")).object_ids == [k1]
    row = only_new_row(lambda: client.get(f"/api/plots/{k1}/risk-checks/"))
    assert (row.endpoint, row.object_ids) == ("plot-risk-checks", [k1])


def test_writes_are_recorded(plot_payload):
    plot_payload["plot_code"] = "KWA-P-AUDITED"
    with patch("apps.registry.tasks.run_risk_check.delay"):
        row = only_new_row(lambda: client_for(AGENT).post("/api/plots/", plot_payload, format="json"))
    assert (row.method, row.status_code, row.object_ids) == ("POST", 201, [plot_id("KWA-P-AUDITED")])


def test_token_requests_are_attributed_to_the_token_user():
    token, _ = Token.objects.get_or_create(user=User.objects.get(username=EXPORTER))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    row = only_new_row(lambda: client.get("/api/farmers/"))
    assert (row.username, row.role) == (EXPORTER, "exporter_partner")


# --- Refused requests are recorded too ---------------------------------------------------------


def test_anonymous_request_is_recorded():
    row = only_new_row(lambda: APIClient().get("/api/farmers/"))
    assert (row.user, row.username, row.role, row.status_code) == (None, "", "", 401)
    assert (row.coordinate_precision, row.commercial_terms) == ("", None)


def test_user_without_a_role_is_recorded(make_staff_user):
    make_staff_user(None, username="grader_user")
    row = only_new_row(lambda: client_for("grader_user").get("/api/deliveries/"))
    assert (row.username, row.role, row.status_code) == ("grader_user", "", 403)


def test_out_of_scope_attempt_is_recorded_with_the_id_asked_for():
    m1 = plot_id("KWA-SEED-M1")
    row = only_new_row(lambda: client_for(AGENT).get(f"/api/plots/{m1}/"))
    assert (row.status_code, row.object_ids) == (404, [m1])


def test_refused_write_is_recorded():
    row = only_new_row(lambda: client_for(AUDITOR).post("/api/deliveries/", {}, format="json"))
    assert (row.method, row.status_code) == ("POST", 403)


@pytest.mark.parametrize(
    "request_",
    [
        lambda c: c.get("/api/status/"),
        lambda c: c.get("/api/price-schedule/"),
        lambda c: c.post("/api/auth/api-token/", {"username": AGENT, "password": "x"}, format="json"),
    ],
    ids=["status", "price-schedule", "login"],
)
def test_public_endpoints_are_not_recorded(request_):
    before = AuditLog.objects.count()
    request_(APIClient())
    assert AuditLog.objects.count() == before


# --- Never the data itself ---------------------------------------------------------------------


def test_rows_never_contain_coordinates_or_national_ids():
    for username in (AGENT, EXPORTER, AUDITOR):
        client = client_for(username)
        client.get("/api/plots/?latitude=-2.540000&longitude=29.710000")
        client.get("/api/farmers/")
        for plot in Plot.objects.filter(plot_code__startswith="KWA-SEED-"):
            client.get(f"/api/plots/{plot.pk}/")
    stored = json.dumps(list(AuditLog.objects.values()), default=str)
    # The masked form, not a bare "6789": that could match the microseconds of a timestamp.
    secrets = {"1198770123456789", "************6789"}
    for plot in Plot.objects.all():
        secrets |= {str(plot.latitude), str(plot.longitude)}
    for sector in Sector.objects.all():
        secrets |= {str(sector.reference_latitude), str(sector.reference_longitude)}
    assert not {secret for secret in secrets if secret in stored}
    assert not AuditLog.objects.filter(path__contains="?").exists()


# --- Append-only -------------------------------------------------------------------------------


def test_rows_cannot_be_changed_or_deleted():
    row = only_new_row(lambda: client_for(AGENT).get("/api/plots/"))
    row.status_code = 200
    with pytest.raises(AppendOnlyError):
        row.save()
    with pytest.raises(AppendOnlyError):
        row.delete()
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.filter(pk=row.pk).update(username="someone-else")
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().delete()
    assert AuditLog.objects.get(pk=row.pk).username == AGENT


def test_admin_is_read_only():
    admin = site._registry[AuditLog]
    request = RequestFactory().get("/")
    request.user = User.objects.create_superuser(username="root", password="x")
    assert not admin.has_add_permission(request)
    assert not admin.has_change_permission(request)
    assert not admin.has_delete_permission(request)


def test_trail_survives_the_user_being_removed():
    row = only_new_row(lambda: client_for(EXPORTER).get("/api/plots/"))
    User.objects.filter(username=EXPORTER).delete()
    row.refresh_from_db()
    assert (row.user, row.username) == (None, EXPORTER)


def test_request_fails_if_the_trail_cannot_be_written():
    client = client_for(AGENT, raise_request_exception=False)
    with patch("apps.audit.middleware.AuditLog.objects.create", side_effect=RuntimeError("db down")):
        assert client.get("/api/plots/").status_code == 500


# --- The audit-log endpoint --------------------------------------------------------------------


def test_only_the_auditor_can_read_the_audit_log(make_staff_user):
    make_staff_user(None, username="grader_user")
    assert client_for(AUDITOR).get("/api/audit-log/").status_code == 200
    for username in (AGENT, EXPORTER, "grader_user"):
        assert client_for(username).get("/api/audit-log/").status_code == 403
    assert APIClient().get("/api/audit-log/").status_code == 401


def test_audit_log_lists_newest_first_and_records_its_own_reads():
    client_for(AGENT).get("/api/plots/")
    client = client_for(AUDITOR)
    first = client.get("/api/audit-log/").json()["results"]
    assert first[0]["username"] == AGENT and first[0]["resource"] == "plots"
    newest = client.get("/api/audit-log/").json()["results"][0]
    assert (newest["username"], newest["resource"], newest["path"]) == (AUDITOR, "audit_log", "/api/audit-log/")


def test_audit_log_filters_by_user_and_status():
    client_for(AGENT).get("/api/plots/")
    client_for(EXPORTER).post("/api/plots/", {}, format="json")
    client = client_for(AUDITOR)
    rows = client.get("/api/audit-log/", {"username": EXPORTER}).json()["results"]
    assert rows and {row["username"] for row in rows} == {EXPORTER}
    rows = client.get("/api/audit-log/", {"status_code": 403}).json()["results"]
    assert rows and {row["status_code"] for row in rows} == {403}


def test_solanges_questions_are_one_query_each():
    """The three questions in the F2 brief, answered from the audit log by URL."""
    client_for(AGENT).get("/api/plots/")
    client_for(AGENT).get("/api/farmers/")
    client_for(EXPORTER).get("/api/plots/")
    client_for(AUDITOR).get("/api/plots/")
    client = client_for(AUDITOR)

    def who(query):
        rows = client.get(f"/api/audit-log/?{query}").json()["results"]
        return {(row["username"], row["resource"]) for row in rows}

    # 1. Who has looked at exact plot coordinates?
    assert who("resource=plots&coordinate_precision=full") == {(AGENT, "plots"), (AUDITOR, "plots")}
    # 2. Who has looked at farmer identity data (the national ID) this season?
    assert who("resource=farmers&national_id=last_four&occurred_after=2026-01-01T00:00:00Z") == {(AGENT, "farmers")}
    # 3. What precision left the system for the buyer?
    rows = client.get("/api/audit-log/?role=exporter_partner&resource=plots").json()["results"]
    assert {row["coordinate_precision"] for row in rows} == {"sector"}


def test_precision_filters_reject_unknown_values():
    response = client_for(AUDITOR).get("/api/audit-log/?coordinate_precision=exact")
    assert response.status_code == 400
