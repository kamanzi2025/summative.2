"""HTTP smoke test for the local Django app and public status route."""

import json
from urllib.request import urlopen

import pytest
from pytest_django.live_server_helper import LiveServer


@pytest.mark.django_db(transaction=True)
def test_local_server_starts_and_serves_public_status(live_server: LiveServer) -> None:
    with urlopen(f"{live_server.url}/api/status/", timeout=10) as response:
        body = json.loads(response.read())
        assert response.status == 200
        assert response.headers.get_content_type() == "application/json"

    assert body["status"] == "ok"
    assert body["service"] == "kawa-api"
    assert set(body["risk_checks"]) == {
        "pending",
        "unverified",
        "stale",
        "requires_manual_review",
        "last_attempt_at",
        "healthy",
    }
