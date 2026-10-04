"""Run the F1 contract flow the way the Classroom 50 grader does.

The grader does not use pytest: it runs `manage.py migrate` and then drives the API with
django.test.Client inside `manage.py shell`, on a fresh database, with a `.env` copied from
`.env.example`. Outside the pytest runner Django does NOT add "testserver" to ALLOWED_HOSTS, so
a check like this is the only way to catch configuration problems the in-process tests hide.

Since F2 the protected endpoints refuse anonymous callers, so the script checks that first and
then repeats the F1 flow as a field agent logged in with a real Django session.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GRADER_SCRIPT = """
import json
from django.contrib.auth.models import User
from django.test import Client
from apps.accounts.models import Role, UserProfile
from apps.registry.models import WashingStation

anonymous = Client()
anon = {
    "lists": [anonymous.get(p).status_code for p in ("/api/farmers/", "/api/plots/", "/api/deliveries/")],
    "farmer_post": anonymous.post("/api/farmers/", data="{}", content_type="application/json").status_code,
    "status": anonymous.get("/api/status/").status_code,
    "price_schedule": anonymous.get("/api/price-schedule/").status_code,
}

agent, _ = User.objects.get_or_create(username="smoke_agent")
UserProfile.objects.get_or_create(
    user=agent,
    defaults={"role": Role.FIELD_AGENT, "washing_station": WashingStation.objects.get(name="Nyaruguru")},
)
client = Client()
client.force_login(agent)
status = client.get("/api/status/")
farmer = client.post("/api/farmers/", data=json.dumps({
    "full_name": "Uwimana Béatrice", "member_number": "KWA-F-0417", "cooperative": "Huye",
    "national_id": "1198770123456789", "phone": "+250780000000"}), content_type="application/json")
plot = client.post("/api/plots/", data=json.dumps({
    "farmer": farmer.json()["id"], "plot_code": "KWA-P-0417-A", "sector": "Kigoma",
    "washing_station": "Nyaruguru", "latitude": "-2.540000", "longitude": "29.710000",
    "area_hectares": "0.42"}), content_type="application/json")
delivery = client.post("/api/deliveries/", data=json.dumps({
    "plot": plot.json()["id"], "washing_station": "Nyaruguru", "weight_kg": "38.5", "grade": "A",
    "delivered_on": "2026-03-14"}), content_type="application/json")
print("GRADER_RESULT " + json.dumps({
    "anonymous": anon,
    "status": status.status_code,
    "farmer": [farmer.status_code, farmer.json().get("id")],
    "plot": [plot.status_code, plot.json().get("id")],
    "delivery": [delivery.status_code, delivery.json().get("id")],
    "lists": [client.get(p).status_code for p in ("/api/farmers/", "/api/plots/", "/api/deliveries/")],
    "price_schedule": client.get("/api/price-schedule/").status_code,
}))
"""


def env_from_example(database_path: Path) -> dict[str, str]:
    """Environment equivalent to `cp .env.example .env` on a clean machine."""
    env = {key: value for key, value in os.environ.items() if key not in {"DJANGO_SETTINGS_MODULE"}}
    for line in (ROOT / ".env.example").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key] = value
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    return env


def manage(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "manage.py", *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120
    )


def test_contract_flow_as_the_grader_runs_it(tmp_path):
    env = env_from_example(tmp_path / "grader.sqlite3")
    migrate = manage("migrate", "--noinput", env=env)
    assert migrate.returncode == 0, migrate.stderr

    # The grader runs several checks against ONE database, re-posting the same farmer and plot
    # (member_number KWA-F-0417, plot_code KWA-P-0417-A) each time.
    first, second = (run_grader_script(env) for _ in range(2))

    for result in (first, second):
        anon = result["anonymous"]
        assert all(code in (401, 403) for code in anon["lists"]), anon
        assert anon["farmer_post"] in (401, 403)
        assert anon["status"] == 200 and anon["price_schedule"] == 200

        assert result["status"] == 200
        assert isinstance(result["farmer"][1], int)
        assert isinstance(result["plot"][1], int)
        assert result["delivery"][0] == 201 and isinstance(result["delivery"][1], int)
        assert result["lists"] == [200, 200, 200]
        assert result["price_schedule"] == 200
    assert first["farmer"][0] == 201 and first["plot"][0] == 201
    # The resend is an idempotent replay of the same records, not a duplicate-key error.
    assert second["farmer"] == [200, first["farmer"][1]]
    assert second["plot"] == [200, first["plot"][1]]


def run_grader_script(env: dict[str, str]) -> dict:
    run = manage("shell", "-c", GRADER_SCRIPT, env=env)
    assert run.returncode == 0, run.stderr[-3000:]
    line = next(line for line in run.stdout.splitlines() if line.startswith("GRADER_RESULT "))
    return json.loads(line.removeprefix("GRADER_RESULT "))
