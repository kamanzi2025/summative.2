"""Authentication: who the caller is. Role-based authorization is tested in test_role_policies.py."""

import base64
from unittest.mock import patch

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.accounts.models import Role

pytestmark = pytest.mark.django_db

PROTECTED_LISTS = ["/api/farmers/", "/api/plots/", "/api/deliveries/"]
PROTECTED = [
    *PROTECTED_LISTS,
    "/api/stations/",
    "/api/farmers/1/",
    "/api/plots/1/",
    "/api/plots/1/risk-checks/",
    "/api/deliveries/1/",
    "/api/stations/1/deliveries/",
]
LOGIN_PATHS = ["/api/auth/staff-login/", "/api/auth/api-token/"]
STAFF_PASSWORD = "GraderPass123!"  # what make_staff_user sets


@pytest.fixture
def grader_user(make_staff_user):
    """The contract's generic credential: a valid user with no role profile."""
    return make_staff_user(None, username="grader_user")


@pytest.fixture
def agent_user(make_staff_user):
    """A user with a role, for flows that go on to call protected endpoints."""
    return make_staff_user(Role.FIELD_AGENT, username="agent")


def credentials(username):
    return {"username": username, "password": STAFF_PASSWORD}


@pytest.mark.parametrize("path", PROTECTED)
def test_anonymous_reads_are_refused(anon_api, path):
    response = anon_api.get(path)
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Token"
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize("path", PROTECTED_LISTS)
def test_anonymous_registrations_reach_validation(anon_api, path):
    """F1 had no login, so the three registrations stay open (ANONYMOUS_POLICY); reads do not."""
    response = anon_api.post(path, {}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_anonymous_f1_flow_registers_but_reveals_nothing(anon_api, farmer_payload, nyaruguru):
    farmer = anon_api.post("/api/farmers/", farmer_payload, format="json")
    assert farmer.status_code == 201, farmer.json()
    assert "national_id" not in farmer.json()
    plot_body = {
        "farmer": farmer.json()["id"],
        "plot_code": "KWA-P-0417-A",
        "sector": "Kigoma",
        "washing_station": "Nyaruguru",
        "latitude": "-2.540000",
        "longitude": "29.710000",
        "area_hectares": "0.42",
    }
    with patch("apps.registry.tasks.run_risk_check.delay"):
        plot = anon_api.post("/api/plots/", plot_body, format="json")
    assert plot.status_code == 201, plot.json()
    assert plot.json()["coordinate_precision"] == "sector"
    delivery = anon_api.post(
        "/api/deliveries/",
        {"plot": plot.json()["id"], "washing_station": "Nyaruguru", "weight_kg": "38.5", "grade": "A"},
        format="json",
    )
    assert delivery.status_code == 201, delivery.json()
    assert "amount_due_rwf" not in delivery.json()
    # Reading back is still refused.
    assert anon_api.get(f"/api/farmers/{farmer.json()['id']}/").status_code == 401
    assert anon_api.get("/api/farmers/").status_code == 401


def test_bearer_token_authenticates_like_token(agent_user):
    token, _ = Token.objects.get_or_create(user=agent_user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.key}")
    assert client.get("/api/farmers/").status_code == 200
    client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
    assert client.get("/api/farmers/").status_code == 401


def test_basic_auth_authenticates(agent_user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Basic " + base64.b64encode(b"agent:" + STAFF_PASSWORD.encode()).decode())
    assert client.get("/api/farmers/").status_code == 200
    client.credentials(HTTP_AUTHORIZATION="Basic " + base64.b64encode(b"agent:wrong").decode())
    assert client.get("/api/farmers/").status_code == 401


@pytest.mark.parametrize("path", ["/api/status/", "/api/price-schedule/"])
def test_status_and_price_schedule_stay_public(anon_api, path):
    assert anon_api.get(path).status_code == 200


@pytest.mark.parametrize("path", LOGIN_PATHS)
def test_login_returns_a_token_for_a_user_without_a_role(anon_api, grader_user, path):
    response = anon_api.post(path, credentials("grader_user"), format="json")
    assert response.status_code == 200
    assert response.json() == {"token": Token.objects.get(user=grader_user).key}


@pytest.mark.parametrize("path", LOGIN_PATHS)
def test_login_returns_the_same_token_each_time(anon_api, grader_user, path):
    body = credentials("grader_user")
    first = anon_api.post(path, body, format="json").json()["token"]
    assert anon_api.post(path, body, format="json").json()["token"] == first
    assert Token.objects.filter(user=grader_user).count() == 1


@pytest.mark.parametrize("path", LOGIN_PATHS)
@pytest.mark.parametrize(
    "body",
    [
        {"username": "grader_user", "password": "wrong"},
        {"username": "nobody", "password": STAFF_PASSWORD},
        {"username": "grader_user"},
        {},
    ],
)
def test_bad_credentials_are_rejected(anon_api, grader_user, path, body):
    response = anon_api.post(path, body, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert not Token.objects.exists()


@pytest.mark.parametrize("path", LOGIN_PATHS)
def test_inactive_user_cannot_log_in(anon_api, grader_user, path):
    grader_user.is_active = False
    grader_user.save()
    response = anon_api.post(path, credentials("grader_user"), format="json")
    assert response.status_code == 400


@pytest.mark.parametrize("path", LOGIN_PATHS)
def test_login_ignores_a_bad_authorization_header(grader_user, path):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
    response = client.post(path, credentials("grader_user"), format="json")
    assert response.status_code == 200


def test_staff_login_starts_a_session_that_authenticates_later_requests(agent_user):
    client = APIClient(enforce_csrf_checks=True)
    response = client.post("/api/auth/staff-login/", credentials("agent"), format="json")
    assert response.status_code == 200
    assert "sessionid" in response.cookies
    assert client.get("/api/farmers/").status_code == 200


def test_api_token_does_not_start_a_session(anon_api, agent_user):
    response = anon_api.post("/api/auth/api-token/", credentials("agent"), format="json")
    assert "sessionid" not in response.cookies
    assert anon_api.get("/api/farmers/").status_code == 401


def test_token_authenticates_requests(anon_api, agent_user):
    token = anon_api.post("/api/auth/api-token/", credentials("agent"), format="json").json()["token"]
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    assert client.get("/api/farmers/").status_code == 200


def test_invalid_token_is_refused():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
    assert client.get("/api/farmers/").status_code == 401


def test_session_writes_require_csrf(agent_user, farmer_payload):
    """A logged-in browser session cannot be ridden by a cross-site form post."""
    client = APIClient(enforce_csrf_checks=True)
    client.login(**credentials("agent"))
    response = client.post("/api/farmers/", farmer_payload, format="json")
    assert response.status_code == 403


def test_token_writes_do_not_need_csrf(agent_user, farmer_payload):
    token, _ = Token.objects.get_or_create(user=agent_user)
    client = APIClient(enforce_csrf_checks=True)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    assert client.post("/api/farmers/", farmer_payload, format="json").status_code == 201
