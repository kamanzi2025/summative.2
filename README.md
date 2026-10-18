# Kawa Network API

Backend for the Kawa Network coffee cooperative. It registers farmers and their plots, records
cherry deliveries at washing stations (starting with Nyaruguru), calculates the amount due from
the price schedule effective on the delivery date, and checks every plot against an external
deforestation-risk registry **in the background**, so a slow or broken registry never blocks
delivery recording. Payment execution is outside this API.

This repository covers the Formative 1 (F1) and Formative 2 (F2) milestones of the `2793` Advanced
Python assessment, and continues into the Summative. F2 retrofits authentication, role-based access
(field agents, exporter partners, compliance auditors), location and ID privacy, and an access
audit log onto the F1 API, without changing its paths.

- **F2 decisions:** [DECISION_LOG.md](DECISION_LOG.md) · **Role model:** [docs/RBAC_MATRIX.md](docs/RBAC_MATRIX.md)
- **Architecture decisions (F1):** [ADR.md](ADR.md)
- **OpenAPI schema:** [schema.yml](schema.yml), live at `/api/schema/`, Swagger UI at `/api/docs/`
- **Autograding contracts:** [F1](docs/autograding/F1_CONTRACT.md) ·
  [Runtime](docs/autograding/RUN_CONTRACT.md) · [F2](docs/autograding/F2_CONTRACT.md) ·
  [Summative](docs/autograding/SUMMATIVE_CONTRACT.md)

## Contents

1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Setup](#setup)
4. [Environment variables](#environment-variables)
5. [Running Redis, the worker and beat](#running-redis-the-celery-worker-and-beat)
6. [Tests and quality checks](#tests-and-quality-checks)
7. [Authentication and roles (F2)](#authentication-and-roles-f2)
8. [API reference with curl examples](#api-reference-with-curl-examples)
9. [Performance: the station delivery feed](#performance-the-station-delivery-feed)
10. [Design notes](#design-notes)
11. [Development history](#development-history)
12. [AI-use disclosure](#ai-use-disclosure)

## Architecture

```mermaid
flowchart LR
    Phone["Station phone (2G)"] -->|HTTPS JSON| API["Django + DRF<br/>(config/, apps/)"]
    API -->|read/write| DB[("SQLite / Postgres")]
    API -->|"on_commit: run_risk_check.delay(plot_id)"| Redis[("Redis broker")]
    Redis --> Worker["Celery worker<br/>run_risk_check"]
    Beat["Celery beat<br/>every 15 min"] -->|requeue_stale_risk_checks| Redis
    Worker -->|"2–40 s, may fail for hours"| Registry["Deforestation-risk registry<br/>(simulated in F1)"]
    Worker -->|"RiskCheckAttempt rows,<br/>plot.risk_status"| DB
```

| Path | Responsibility |
|---|---|
| `config/` | Settings (all read from env), URL root, `celery.py` |
| `apps/core/` | Error envelope (`exceptions.py`), cursor pagination (`pagination.py`), JSON logging, `/api/status/`, `seed_demo` command |
| `apps/registry/` | `Sector`, `WashingStation`, `Farmer`, `Plot`, `RiskCheckAttempt`; registry client (`clients.py`); Celery tasks (`tasks.py`); services |
| `apps/pricing/` | `PriceSchedule` / `PriceEntry` (dated active schedules), `/api/price-schedule/` |
| `apps/deliveries/` | `Delivery` (plot-linked, price and risk snapshots, idempotency key), station feed |
| `apps/accounts/` | F2: `UserProfile` (role + station), `ROLE_POLICIES`, permission class, `visible_to()` scoping, field rules (masking, coarsening), login endpoints, `seed_rbac_fixtures` |
| `apps/audit/` | F2: append-only `AuditLog`, the middleware that writes it, `/api/audit-log/` |
| `tests/` | pytest suite, including mirrors of the F1 contract payloads and the F2 access matrix |

Views are thin. Validation lives in serializers (field and cross-field `validate()`), and
business operations live in each app's `services.py`, which both views and Celery tasks call.
Access control has four layers, each answering one question: the permission class (may this role
call this endpoint?), the queryset (`visible_to(user)`: which records?), serializer fields (which
fields, at what precision?), and the audit middleware (who saw what?). See
[docs/RBAC_MATRIX.md](docs/RBAC_MATRIX.md).

**Request flow for a new plot:** `POST /api/plots/` → the serializer validates it → the
`register_plot` service saves it with `risk_status="pending"` → `201` is returned in
milliseconds → **after commit**, `run_risk_check.delay(plot_id)` is published → the worker calls
the registry, records a `RiskCheckAttempt` and sets the plot to `clear` or `flagged` → on failure
it retries with exponential backoff and jitter → when retries run out the plot becomes
`unverified` → beat's `requeue_stale_risk_checks` tries it again later.

## Prerequisites

- Python **3.11+** (developed on 3.12)
- Redis 7 for the real async flow. The easiest route is Docker (`docker compose up -d redis`);
  any local Redis on `localhost:6379` also works.
- Optional: Postgres, if you set `DATABASE_URL`.

## Setup

```bash
git clone https://github.com/ALU-BSE/advanced-python-programming-kawa-kamanzi2025.git
cd advanced-python-programming-kawa-kamanzi2025

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                 # defaults work for local SQLite
python manage.py migrate             # also seeds sectors (with reference points), stations, prices
python manage.py seed_rbac_fixtures  # the three role users + F2 fixture farmer, plots, deliveries
python manage.py seed_demo           # optional: demo farmers, plots and deliveries (idempotent)
python manage.py runserver
```

Then open <http://127.0.0.1:8000/api/docs/> for Swagger UI. `/api/status/`,
`/api/price-schedule/`, and the login endpoints are public. Anonymous callers may also use the F1
farmer, plot, and delivery registration POSTs; all protected reads and all requests by authenticated
users to protected resources require an assigned role. See
[Authentication and roles](#authentication-and-roles-f2).

`seed_rbac_fixtures` is safe to run repeatedly (it updates rather than duplicates) and writes
directly to the database, so it needs no Redis or worker. It creates `field_agent_user`
(Nyaruguru), `exporter_user` and `auditor_user`, all with password `GraderPass123!`. These are
**test accounts with a published password: never run it against a production database.**

`migrate` runs data migrations that create the **reference data** the API refers to by name:
sectors (Kigoma, Mbazi, Kibeho, Ngera, Ruheru, Runda), washing stations **Nyaruguru** (`NYR`) and
**Kamonyi** (`KMY`), and an active **2026A** price schedule (A: 760, B: 500, C: 300 RWF/kg; these
are placeholder prices to replace in the admin). A freshly migrated database can therefore accept
the contract's example requests straight away.

## Environment variables

All settings are read in `config/settings.py` with `django-environ`. `.env` is git-ignored; copy
it from `.env.example`.

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | insecure dev key | Django secret. **Set a real value outside local dev.** |
| `DEBUG` | `False` | Debug mode (`.env.example` sets `True` for local work) |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated host names |
| `DATABASE_URL` | `sqlite:///db.sqlite3` | e.g. `postgres://kawa:kawa@localhost:5432/kawa` |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Kept for tooling. Task results are ignored because outcomes live in `RiskCheckAttempt`. |
| `CELERY_BROKER_TRANSPORT_OPTIONS` | `{}` | JSON transport options (e.g. for the filesystem broker) |
| `CELERY_TASK_ALWAYS_EAGER` | `False` | `True` runs tasks inline with no worker. Only for quick demos: requests then wait for the registry. |
| `REGISTRY_API_URL` | *(empty)* | Empty selects the simulator. A non-empty URL currently fails closed until the provider's HTTP contract is confirmed. |
| `REGISTRY_API_TIMEOUT` | `30` | Simulator call timeout; a real registry client is not enabled until its API contract is confirmed |
| `RISK_REGISTRY_MIN_LATENCY` | `2` | Simulated registry: minimum latency (s) |
| `RISK_REGISTRY_MAX_LATENCY` | `40` | Simulated registry: maximum latency (s) |
| `RISK_REGISTRY_FAILURE_RATE` | `0.2` | Simulated registry: chance a call fails with 503. `1.0` forces an outage. |
| `RISK_REGISTRY_FLAG_RATE` | `0.1` | Simulated registry: chance a successful check returns `flagged` |
| `RISK_CHECK_MAX_RETRIES` | `8` | Retries before a plot becomes `unverified` |
| `RISK_CHECK_BACKOFF_SECONDS` | `60` | Backoff base: retry *n* waits random(0, min(base × 2ⁿ, 3600)) s, so up to about 3 h in total |
| `RISK_CHECK_STALE_HOURS` | `6` | The sweeper re-enqueues pending/unverified plots with no attempt in this window |
| `RISK_CHECK_MANUAL_REVIEW_DAYS` | `7` | After this many days `unverified`, `requires_manual_review` becomes `true` |
| `RISK_CHECK_SWEEP_MINUTES` | `15` | How often beat runs `requeue_stale_risk_checks` |
| `PRICE_SCHEDULE_MAX_AGE_SECONDS` | `60` | `Cache-Control: max-age` on `/api/price-schedule/` |
| `LOG_LEVEL` | `INFO` | Root log level (logs are one JSON object per line) |

## Running Redis, the Celery worker and beat

The risk check needs three processes besides Django. Run each in its own terminal, from the
activated virtualenv:

```bash
# 1. Redis (broker)
docker compose up -d redis

# 2. Celery worker: executes run_risk_check
celery -A config worker -l info

# 3. Celery beat: schedules requeue_stale_risk_checks every 15 minutes
celery -A config beat -l info
```

To run everything in containers instead (web, worker, beat and Redis):
`docker compose --profile app up --build`.

To watch the retry path, restart the worker with a forced outage:

```bash
RISK_REGISTRY_FAILURE_RATE=1.0 RISK_REGISTRY_MAX_LATENCY=1 RISK_CHECK_BACKOFF_SECONDS=1 \
  celery -A config worker -l info
```

Register a plot, then read `GET /api/plots/{id}/risk-checks/`. You will see one `error` attempt per
retry, spaced out by exponential backoff, and after 9 attempts (about 4 minutes with a 1-second
base) the plot turns `unverified`. With the production default of 60 seconds, the same chain spans
up to about 3 hours, which is long enough to ride out a typical registry outage.

**If Redis is down,** `POST /api/plots/` still returns `201` in well under a second. The failed
enqueue is logged as `risk_check.enqueue_failed`, the plot stays `pending`, and the beat sweeper
queues it once the broker is back. (Measured locally: 0.49 s with no Redis running.)

## Tests and quality checks

Run everything CI runs with `make check`, or step by step:

```bash
python -m pytest -q                                   # full suite
ruff check .                                          # lint
ruff format --check .                                 # formatting
mypy apps config manage.py                            # static types (django-stubs, drf-stubs)
python manage.py check
python manage.py spectacular --file schema.yml --validate   # regenerate + validate OpenAPI
```

Tests never sleep and never need Redis. Celery tasks are executed with `task.apply()`, and the
registry client is mocked. What the suite covers:

| Area | File |
|---|---|
| The exact F1 contract payloads and list envelopes | `tests/test_contract.py` |
| Farmer phone normalisation and validation errors | `tests/test_farmers.py` |
| Plot is `201` + `pending`, enqueued **on commit**, registry **not** called inline, broker outage tolerated, filters, manual-review queue, validation errors | `tests/test_plots.py` |
| Price and risk snapshots, idempotent replay (`200`, same id), replay with a different body (`409`), exportability policy, validation errors | `tests/test_deliveries.py` |
| Cursor pagination shape, `next` link, stability under inserts, query count, `EXPLAIN` uses the composite index, `since`/grade/risk/exportable filters | `tests/test_feed.py` |
| Task success, retries, capped backoff (3 h worst case), soft time limit → `timeout` + retry, exhaustion → `unverified`, unique attempt numbers, idempotency, sweeper (including abandoned attempts), simulated registry | `tests/test_risk_checks.py` |
| Price-schedule shape and cache header, one-active-schedule constraint, error envelope (400/404/405) | `tests/test_pricing_and_errors.py` |
| F2: login endpoints, session and token auth, CSRF on session writes, anonymous `401` on protected reads | `tests/test_auth.py` |
| F2: `ROLE_POLICIES` (deny by default, read-only roles, matrix values), profile constraints | `tests/test_role_policies.py` |
| F2: `seed_rbac_fixtures` values and idempotency, historical price selection; demo seed date/pricing consistency | `tests/test_seed_rbac_fixtures.py`, `tests/test_seed_demo.py` |
| F2: permission matrix, station scoping on lists, detail routes, sub-routes, writes and replays | `tests/test_access_scoping.py` |
| F2: auditor can read delivery metadata while `unit_price_rwf` and `amount_due_rwf` are absent | `tests/test_access_scoping.py::test_auditor_can_read_delivery_metadata_without_commercial_terms` |
| F2: sector reference points never equal a rounding of a fixture coordinate | `tests/test_sector_reference_points.py` |
| F2: national-ID masking, exporter coarsening (incl. nested copies), auditor without prices | `tests/test_field_rules.py` |
| F2: one append-only audit row per protected request, never coordinates, auditor-only endpoint | `tests/test_audit_log.py` |

CI (`.github/workflows/ci.yml`) runs ruff (lint and format), mypy, `check`, the migration check, schema freshness and
pytest on every push to `main`.

## Authentication and roles (F2)

**Two ways to log in, one `request.user`.**

| Who | Endpoint | Then send |
|---|---|---|
| Staff in a browser or the admin | `POST /api/auth/staff-login/` | the `sessionid` cookie it sets (and the CSRF token on writes) |
| System integrations and scripts | `POST /api/auth/api-token/` | `Authorization: Token <key>` |

Both take `{"username", "password"}` and return `{"token": "<key>"}`. Logging in only proves who
you are. What you may see comes from your **role** (`UserProfile`), and a user without one is
refused (`403`) on every protected endpoint.

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/api-token/ -H 'Content-Type: application/json' \
  -d '{"username": "exporter_user", "password": "GraderPass123!"}' | python -c 'import json,sys; print(json.load(sys.stdin)["token"])')
curl -s http://127.0.0.1:8000/api/plots/ -H "Authorization: Token $TOKEN"
```

**The roles** (full matrix and reasoning in [docs/RBAC_MATRIX.md](docs/RBAC_MATRIX.md)):

| Role | Sees | Writes | National ID | Plot coordinates | Prices | Audit log |
|---|---|---|---|---|---|---|
| `field_agent` | own washing station only | farmers, plots, deliveries at own station | last 4 digits | full | yes | no |
| `exporter_partner` | all stations | nothing | absent | sector reference point | yes | no |
| `compliance_auditor` | all stations | nothing | absent | full | absent | read |

### Example requests per role

Real responses from a freshly migrated database after `seed_rbac_fixtures` (lists trimmed to the
rows that show the difference).

**No credentials:** every protected endpoint is `401`.

```bash
curl -s http://127.0.0.1:8000/api/plots/
```
```json
{"error": {"code": "not_authenticated", "message": "Authentication credentials were not provided.", "details": {}}}
```

**`field_agent_user` (Nyaruguru):** only the Nyaruguru plots, full coordinates, national ID masked.

```bash
curl -s http://127.0.0.1:8000/api/plots/ -H "Authorization: Token $AGENT_TOKEN"
curl -s http://127.0.0.1:8000/api/farmers/ -H "Authorization: Token $AGENT_TOKEN"
```
```json
{"results": [{"plot_code": "KWA-SEED-K2", "sector": "Kigoma", "washing_station": "Nyaruguru",
              "latitude": "-2.660000", "longitude": "29.790000", "coordinate_precision": "full", "...": "..."},
             {"plot_code": "KWA-SEED-K1", "sector": "Kigoma", "washing_station": "Nyaruguru",
              "latitude": "-2.540000", "longitude": "29.710000", "coordinate_precision": "full", "...": "..."}]}
{"results": [{"id": 1, "full_name": "Uwimana Béatrice", "member_number": "KWA-F-SEED-01",
              "phone": "+250788999001", "national_id": "************6789", "home_station": null, "...": "..."}]}
```

Another station's record is `404`, exactly like one that does not exist:

```bash
curl -s http://127.0.0.1:8000/api/plots/3/ -H "Authorization: Token $AGENT_TOKEN"   # KWA-SEED-M1, Kamonyi
```
```json
{"error": {"code": "not_found", "message": "No Plot matches the given query.", "details": {}}}
```

**`exporter_user`:** every station, but each plot reports its sector's reference point, so plots
in one sector are indistinguishable. No `national_id` field at all. Writes are refused.

```bash
curl -s http://127.0.0.1:8000/api/plots/ -H "Authorization: Token $EXPORTER_TOKEN"
curl -s -X POST http://127.0.0.1:8000/api/farmers/ -H "Authorization: Token $EXPORTER_TOKEN" \
  -H 'Content-Type: application/json' -d '{}'
```
```json
{"results": [{"plot_code": "KWA-SEED-M2", "sector": "Mbazi", "latitude": "-2.616000", "longitude": "29.673000", "coordinate_precision": "sector", "...": "..."},
             {"plot_code": "KWA-SEED-M1", "sector": "Mbazi", "latitude": "-2.616000", "longitude": "29.673000", "coordinate_precision": "sector", "...": "..."},
             {"plot_code": "KWA-SEED-K2", "sector": "Kigoma", "latitude": "-2.556000", "longitude": "29.688000", "coordinate_precision": "sector", "...": "..."},
             {"plot_code": "KWA-SEED-K1", "sector": "Kigoma", "latitude": "-2.556000", "longitude": "29.688000", "coordinate_precision": "sector", "...": "..."}]}
{"error": {"code": "permission_denied", "message": "Your role does not allow this.", "details": {}}}
```

**`auditor_user`:** every station, full coordinates, deliveries without `unit_price_rwf` or
`amount_due_rwf`, and the audit log.

```bash
curl -s http://127.0.0.1:8000/api/deliveries/ -H "Authorization: Token $AUDITOR_TOKEN"
curl -s 'http://127.0.0.1:8000/api/audit-log/?page_size=1' -H "Authorization: Token $AUDITOR_TOKEN"
```
```json
{"results": [{"id": 2, "client_reference": "seed-rbac-M1", "washing_station": "Kamonyi", "plot": 3,
              "plot_code": "KWA-SEED-M1", "farmer_name": "Uwimana Béatrice", "weight_kg": "38.50",
              "grade": "A", "delivered_on": "2026-03-14", "recorded_at": "2026-10-04T20:33:11.300311+02:00",
              "is_exportable": false}, "..."]}
{"results": [{"id": 12, "occurred_at": "2026-10-04T20:33:27.272891+02:00", "username": "exporter_user",
              "role": "exporter_partner", "method": "POST", "path": "/api/farmers/", "endpoint": "farmer-list",
              "status_code": 403, "resource": "farmers", "object_ids": [], "coordinate_precision": "sector",
              "national_id": "hidden", "commercial_terms": true}]}
```

### The audit log

Every request to a protected endpoint, including refused ones, writes one append-only `AuditLog`
row: user, role, route, status, the IDs of the records returned, and the field rules applied
(coordinate precision, national-ID handling, whether prices were included). It never stores
coordinates, national IDs, prices, bodies or query strings. `GET /api/audit-log/` (auditors
only) filters by `username`, `role`, `resource`, `status_code`, `coordinate_precision`,
`national_id`, `occurred_after` and `occurred_before`, so each of the brief's three questions is
one request (for example "who saw exact coordinates?" is
`?resource=plots&coordinate_precision=full`). See
[docs/RBAC_MATRIX.md](docs/RBAC_MATRIX.md#solanges-three-questions).

## API reference with curl examples

Base URL: `http://127.0.0.1:8000`. All bodies are JSON. Money and weights are **decimal strings**,
never floats. Protected reads require `-H "Authorization: Token $TOKEN"` (or a session).
Registration POSTs for farmers, plots and deliveries also permit anonymous F1 callers, with no
national ID, sector reference coordinates, and no commercial terms in responses. These writes do
not grant access to subsequent reads. An authenticated account without an active, valid role
profile receives `403` on protected resource reads and writes. Assigned roles follow the matrix in
[docs/RBAC_MATRIX.md](docs/RBAC_MATRIX.md), including field-agent station scoping. The examples
assume a **field agent** at Nyaruguru. The "Roles" column says who may call each endpoint (R read,
W write).

| Method | Path | Purpose | Roles |
|---|---|---|---|
| GET | `/api/status/` | Database-dependent API status and risk-check backlog | public |
| POST | `/api/auth/staff-login/`, `/api/auth/api-token/` | Log in (session / token) | public |
| POST, GET | `/api/farmers/` | Register / list farmers | anonymous W; agent RW; exporter, auditor R |
| GET | `/api/farmers/{id}/` | One farmer | all three roles R |
| POST, GET | `/api/plots/` | Register a plot (async risk check) / list with filters | anonymous W; agent RW; exporter, auditor R |
| GET | `/api/plots/{id}/` | One plot | all three roles R |
| GET | `/api/plots/{id}/risk-checks/` | Registry attempt history for a plot | all three roles R |
| POST, GET | `/api/deliveries/` | Record a delivery (idempotent) / delivery feed | anonymous W; agent RW; exporter, auditor R |
| GET | `/api/deliveries/{id}/` | One delivery | all three roles R |
| GET | `/api/stations/`, `/api/stations/{id}/` | Washing stations | all three roles R |
| GET | `/api/stations/{id}/deliveries/` | One station's delivery feed | all three roles R |
| GET | `/api/audit-log/` | Access audit trail | auditor R |
| GET | `/api/price-schedule/` | Active season's per-grade prices | public |
| GET | `/api/schema/`, `/api/docs/` | OpenAPI schema, Swagger UI | public |

A field agent sees only their own station's records; see the [role table](#authentication-and-roles-f2).

### Status

```bash
curl -s http://127.0.0.1:8000/api/status/
```
```json
{"status": "ok", "service": "kawa-api", "time": "2026-09-29T18:30:22.786299Z",
 "risk_checks": {"pending": 3, "unverified": 0, "stale": 0, "requires_manual_review": 0,
                 "last_attempt_at": "2026-09-29T18:29:51.120Z", "healthy": true}}
```

`/api/status/` is public and database-dependent: producing the backlog snapshot queries the
database. `status: "ok"` means the API handled the request and that query succeeded. A registry,
broker, or worker outage does not directly change that value. `risk_checks.healthy` means the
backlog calculation found no plots beyond the configured staleness threshold; it is an indirect
signal, not a Redis or Celery worker ping. A stopped worker may not be visible until work becomes
stale, and this endpoint is not a full dependency-readiness check.

### Register a farmer

Phones are accepted as `+2507XXXXXXXX`, `2507XXXXXXXX` or `07XXXXXXXX` (MTN/Airtel) and stored in
E.164. `national_id` is optional but, when present, must be 16 digits and unique. It is stored in
full but read back masked to its last 4 digits (and not at all for exporters and auditors). A
farmer registered by a field agent gets the agent's station as `home_station`.

```bash
curl -s -X POST http://127.0.0.1:8000/api/farmers/ -H "Authorization: Token $TOKEN" \
  -H 'Content-Type: application/json' -d '{
  "full_name": "Mukamana Claudine", "member_number": "KWA-F-0418", "cooperative": "Huye",
  "national_id": "1198870123450001", "phone": "+250780000001"}'
```
```json
{"id": 4, "full_name": "Mukamana Claudine", "member_number": "KWA-F-0418", "cooperative": "Huye",
 "phone": "+250780000001", "national_id": "************0001", "home_station": "Nyaruguru",
 "created_at": "2026-09-29T20:30:22.817202+02:00"}
```

### Register a plot (returns immediately, check runs in background)

`sector` and `washing_station` are given by name. Coordinates must fall inside Rwanda's bounding
box, and the area must be between 0 and 50 ha. A field agent can register plots only at their own
station, for farmers they can see.

```bash
curl -s -X POST http://127.0.0.1:8000/api/plots/ -H "Authorization: Token $TOKEN" \
  -H 'Content-Type: application/json' -d '{
  "farmer": 4, "plot_code": "KWA-P-0417-A", "sector": "Kigoma", "washing_station": "Nyaruguru",
  "latitude": "-2.540000", "longitude": "29.710000", "area_hectares": "0.42"}'
```
```json
{"id": 6, "farmer": 4, "plot_code": "KWA-P-0417-A", "label": "", "sector": "Kigoma",
 "washing_station": "Nyaruguru", "latitude": "-2.540000", "longitude": "29.710000",
 "area_hectares": "0.4200", "risk_status": "pending", "risk_checked_at": null,
 "requires_manual_review": false, "coordinate_precision": "full",
 "created_at": "2026-09-29T20:31:35.170000+02:00"}
```

### List plots (filters: `farmer`, `sector`, `washing_station`, `risk_status`, `requires_manual_review`)

`GET /api/plots/?requires_manual_review=true` is the manual-review queue: plots still
`unverified` after `RISK_CHECK_MANUAL_REVIEW_DAYS`.

```bash
curl -s 'http://127.0.0.1:8000/api/plots/?risk_status=pending&page_size=1' -H "Authorization: Token $TOKEN"
```
```json
{"next": "http://127.0.0.1:8000/api/plots/?cursor=cD0yMDI2LTA5LTI5KzE4JTNBMzMlM0ExMS42Nzg0OTIlMkIwMCUzQTAw&page_size=1&risk_status=pending",
 "previous": null,
 "results": [{"id": 11, "farmer": 4, "plot_code": "KWA-P-DOWN-1", "sector": "Kigoma",
              "washing_station": "Nyaruguru", "risk_status": "pending", "...": "..."}]}
```

### Risk-check history

```bash
curl -s http://127.0.0.1:8000/api/plots/11/risk-checks/ -H "Authorization: Token $TOKEN"
```
```json
[{"attempt_number": 1, "outcome": "error", "started_at": "2026-09-29T20:33:12.72+02:00",
  "finished_at": "2026-09-29T20:33:12.88+02:00", "duration_ms": 166,
  "error_message": "registry returned 503 Service Unavailable", "task_id": "f5822d6a-..."},
 {"attempt_number": 2, "outcome": "error", "...": "..."}]
```

### Record a delivery

The station must be the plot's station. `delivered_on` defaults to today and cannot be in the
future. The price comes from the schedule effective on `delivered_on` and is snapshotted when the
request is recorded.
`client_reference` is the phone's idempotency key (optional, unique per station).

```bash
curl -s -i -X POST http://127.0.0.1:8000/api/deliveries/ -H "Authorization: Token $TOKEN" \
  -H 'Content-Type: application/json' -d '{
  "plot": 1, "washing_station": "Nyaruguru", "weight_kg": "35.5", "grade": "A",
  "client_reference": "nyr-phone-02-0040"}'
```
```
HTTP/1.1 201 Created
Idempotent-Replayed: false
```
```json
{"id": 46, "plot": 1, "plot_code": "KWA-P-DEMO-01", "farmer": 1, "farmer_name": "Mukamana Claudine",
 "washing_station": "Nyaruguru", "weight_kg": "35.50", "grade": "A", "delivered_on": "2026-09-29",
 "client_reference": "nyr-phone-02-0040", "season": "2026A", "unit_price_rwf": "760.00",
 "amount_due_rwf": "26980.00", "plot_risk_status_at_delivery": "clear", "is_exportable": true,
 "recorded_at": "2026-09-29T20:33:57.340481+02:00"}
```

**Replaying the same request** (the 2G connection dropped before the phone saw the response)
returns the original delivery rather than creating a duplicate:

```
HTTP/1.1 200 OK
Idempotent-Replayed: true
```
```json
{"id": 46, "client_reference": "nyr-phone-02-0040", "amount_due_rwf": "26980.00", "...": "..."}
```

**Reusing a `client_reference` with different values** (a phone bug, not a retry) is refused, so
the phone is never told a wrong delivery was saved:

```json
HTTP/1.1 409 Conflict
{"error": {"code": "conflict",
  "message": "client_reference 'nyr-phone-02-0040' was already used for record 46 with different details.",
  "details": {"id": 46, "mismatched_fields": ["weight_kg"]}}}
```

### Error responses

Every error uses one envelope: `{"error": {"code", "message", "details"}}`.

```bash
curl -s -X POST http://127.0.0.1:8000/api/deliveries/ -H "Authorization: Token $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"plot": 1, "washing_station": "Kamonyi", "weight_kg": "-3", "grade": "A", "delivered_on": "2030-01-01"}'
```
```json
{"error": {"code": "validation_error", "message": "The request data is invalid.",
  "details": {"washing_station": ["Object with name=Kamonyi does not exist."],
              "weight_kg": ["Must be greater than 0."],
              "delivered_on": ["Delivery date cannot be in the future."]}}}
```

For a field agent at Nyaruguru, Kamonyi is outside their scope, so it fails as "does not exist",
the same as a name that really does not exist. The cross-field rule that a delivery's station must be its plot's station
(`"Plot KWA-P-DEMO-01 delivers to Nyaruguru, not Kamonyi."`) still runs, as a second line of
defence.

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | Field or cross-field rule failed (`details` maps field → messages) |
| 400 | `parse_error` | Malformed JSON |
| 401 | `not_authenticated` / `authentication_failed` | No credentials, or an invalid token (header `WWW-Authenticate: Token`) |
| 403 | `permission_denied` | Authenticated user has no valid assigned role, or the assigned role may not do this; also a session write without a CSRF token |
| 404 | `not_found` | Unknown id or route, **or a record outside a field agent's station** (never `403`, so its existence is not confirmed), e.g. `{"error": {"code": "not_found", "message": "No Farmer matches the given query.", "details": {}}}` |
| 405 | `method_not_allowed` | e.g. `DELETE /api/price-schedule/` |
| 409 | `conflict` | A natural key (`member_number`, `plot_code`, or a station's `client_reference`) was reused with different details (`details.mismatched_fields`), or two requests raced past validation into a DB uniqueness constraint |
| 500 | `server_error` | Unexpected failure. The traceback is logged, never returned. |

**Resends are replays, not errors.** Every create is idempotent on its natural key: a farmer's
`member_number`, a plot's `plot_code`, and a delivery's `client_reference` (per station). On 2G a
phone often resends a request whose response it never received, so:

- An **identical resend** returns the existing record with **200** and `Idempotent-Replayed: true`.
  Nothing is duplicated, and a plot's risk check is not queued twice.
- The **same key with different details** is a real conflict: **409**, with
  `details.mismatched_fields` so the app can show what differs.
- A duplicate on a *secondary* unique field (for example, a phone number already used by another
  member) is a **400** validation error on that field, so the app can highlight it.

### Station delivery feed (cursor-paginated)

`GET /api/deliveries/` and `GET /api/stations/{id}/deliveries/` return the same slim rows, newest
first. Filters: `washing_station` (name, on `/api/deliveries/`), `grade`, `risk_status` (the plot's
*current* status), `exportable` (`true`/`false`), and `since` (ISO datetime, strictly newer than
`recorded_at`). The review list of recorded-but-flagged cherry is
`?exportable=false&risk_status=flagged`. Use `page_size`
to change the page length (default 20, maximum 100).

```bash
curl -s 'http://127.0.0.1:8000/api/stations/1/deliveries/?page_size=2' -H "Authorization: Token $TOKEN"
```
```json
{
  "next": "http://127.0.0.1:8000/api/stations/1/deliveries/?cursor=cD0yMDI2LTA5LTI5KzE4JTNBMzMlM0E1Ny4yMjQ3NjMlMkIwMCUzQTAw&page_size=2",
  "previous": null,
  "results": [
    {"id": 46, "client_reference": "nyr-phone-02-0040", "washing_station": "Nyaruguru", "plot": 1,
     "plot_code": "KWA-P-DEMO-01", "farmer_name": "Mukamana Claudine", "weight_kg": "35.50",
     "grade": "A", "amount_due_rwf": "26980.00", "delivered_on": "2026-09-29",
     "recorded_at": "2026-09-29T20:33:57.340481+02:00", "is_exportable": true},
    {"id": 45, "client_reference": "nyr-phone-02-0039", "washing_station": "Nyaruguru", "plot": 6,
     "plot_code": "KWA-P-0417-C", "farmer_name": "Uwimana Béatrice", "weight_kg": "34.50",
     "grade": "B", "amount_due_rwf": "17250.00", "delivered_on": "2026-09-29",
     "recorded_at": "2026-09-29T20:33:57.224763+02:00", "is_exportable": true}
  ]
}
```

Follow `next` exactly as given; the cursor is opaque. To poll for new rows only, pass the newest
`recorded_at` the phone holds **minus a 2-minute overlap**, and de-duplicate by `id`:
`/api/stations/1/deliveries/?since=2026-09-29T20:31:57%2B02:00`. The overlap covers deliveries
whose write committed slightly after a newer one (`recorded_at` is stamped at write time, not
commit time), so a slow transaction can never be skipped. See ADR-002.

### Price schedule

```bash
curl -s -i http://127.0.0.1:8000/api/price-schedule/
```
```
HTTP/1.1 200 OK
Cache-Control: public, max-age=60
```
```json
{"id": 1, "season": "2026A", "effective_from": "2026-03-01", "currency": "RWF", "unit": "kg",
 "prices": [{"grade": "A", "price_per_kg_rwf": "760.00"},
            {"grade": "B", "price_per_kg_rwf": "500.00"},
            {"grade": "C", "price_per_kg_rwf": "300.00"}]}
```

**Cache invalidation:** there is **no server-side cache**. Every request reads the active
schedule from the database, so a price change (or activating a new schedule with
`apps.pricing.services.activate_schedule`) is served by the very next request. The only caching is
the `Cache-Control: max-age=60` header, so a client or proxy may show the old prices for **at most
60 seconds** (`PRICE_SCHEDULE_MAX_AGE_SECONDS`). A future-dated schedule can be activated in
advance; the previous schedule remains effective until the new schedule's `effective_from` date.
Delivery pricing never uses a cached value; it selects the schedule effective on `delivered_on`
and stores that price on the delivery when the request is recorded.

**Pricing assumption:** active schedules form one global effective-date timeline across season
labels; `season` is descriptive, not a separate price-selection boundary. The latest active
`effective_from` date on or before the delivery date wins. An active schedule cannot share its
effective date with another active schedule, regardless of season. This is the project's chosen
domain assumption; the F1/F2/Summative contracts do not define cross-season precedence.

## Performance: the station delivery feed

**Assessed feature: cursor pagination of the station delivery feed.** The full reasoning is in
[ADR-002](ADR.md#adr-002-whose-performance-problem-to-solve-first-the-station-delivery-feed).

- **Why cursor, not offset.** During the harvest peak, Nyaruguru records about 400 deliveries a
  day (a volume estimate, not a concurrency specification), and they land at the top of the feed
  while Emmanuel is scrolling. With `?page=2` (offset),
  every new row pushes older rows down a page, so he sees duplicates or misses rows. `OFFSET n`
  also makes the database read and throw away `n` rows, so later pages get slower as the table
  grows. A cursor (`WHERE (recorded_at, id) < last seen … LIMIT 20`) is stable under inserts and
  costs the same on page 1 and page 500. `test_cursor_is_stable_when_new_rows_arrive_between_pages`
  proves the stability.
- **Index, verified with `EXPLAIN`.** The composite index
  `Delivery(washing_station, -recorded_at, -id)` matches the feed's `WHERE` and `ORDER BY`
  (`apps/deliveries/models.py`). SQLite's plan for a later page of the station feed:

  ```
  SEARCH deliveries_delivery USING INDEX delivery_station_feed_idx (washing_station_id=? AND recorded_at<?)
  SEARCH registry_plot USING INTEGER PRIMARY KEY (rowid=?)
  SEARCH registry_farmer USING INTEGER PRIMARY KEY (rowid=?)
  SEARCH registry_washingstation USING INTEGER PRIMARY KEY (rowid=?)
  ```

  This is an index range scan with no `USE TEMP B-TREE FOR ORDER BY`, so there is no sort, and the
  joins are primary-key lookups. `test_station_feed_query_uses_composite_index` fails if the plan
  ever regresses. To reproduce:
  `python manage.py shell -c "from apps.deliveries.services import feed_queryset; print(feed_queryset().filter(washing_station_id=1)[:21].explain())"`
- **The other lists are indexed too.** `GET /api/farmers/` and `GET /api/plots/` use the same
  cursor ordering `(-created_at, -id)`, backed by `farmer_list_cursor_idx` and
  `plot_list_cursor_idx`. A later page plans as
  `SEARCH registry_plot USING INDEX plot_list_cursor_idx (created_at<?)`, and
  `test_list_endpoints_page_through_an_index` guards both.
- **No N+1.** `select_related("plot__farmer", "washing_station")` makes each page **one SQL query**
  (two for the station route, including the station lookup that returns 404), plus, since F2, the
  one `INSERT` into the audit log. Tests assert this with `django_assert_num_queries` and check
  that the extra query is the audit insert. Station scoping is a `WHERE` on the same indexed
  column, so it adds no query.
- **No `COUNT(*)`.** Cursor pagination does not count the table, unlike page-number pagination.
- **Small payloads for 2G.** The feed serializer is flat (no nested plot or farmer objects).
  Reproducible local benchmark runs measure a 20-row page at **8,774 bytes raw** and have recorded
  **684–747 bytes gzip** for synthetic data. See [the benchmark assumptions and results](docs/PERFORMANCE_BENCHMARK.md);
  it measures one sequential agent session on temporary SQLite and is not a concurrent capacity claim.
- **Incremental sync.** `?since=` lets the phone download only rows newer than the newest one it
  has.

## Design notes

See **[ADR.md](ADR.md)** for:

- **ADR-001, accept-then-verify:** why the deforestation-risk check is an asynchronous, retried
  status on the plot, why deliveries are never blocked by it, and the policy for plots whose check
  never succeeds (deliveries are recorded with payment snapshots, remain non-exportable until
  `clear`, and flagged deliveries are surfaced for review, with manual review after 7 days
  `unverified`). Payment execution is outside this API.
- **ADR-002:** why Emmanuel's feed was optimised before the pricing path.
- **ADR-003:** why every create is idempotent on its natural key, and why that beats an
  `Idempotency-Key` header or plain `400`s for 2G retries.

Other decisions worth knowing:

- **A delivery references a plot, not a farmer.** The farmer is reached through the plot, which
  keeps the provenance chain export lot → delivery → plot → land intact.
- **Snapshots:** `unit_price_rwf`, `amount_due_rwf` and `plot_risk_status_at_delivery` are copied
  onto the delivery, so later price changes or risk verdicts never rewrite history.
  `is_exportable`, `export_status` and `export_status_reason` are computed from the plot's *current*
  status; unknown or unverified risk is held from export.
- **Sectors and stations are models**, referenced by name in the API. F2 scopes field agents by
  washing station and serves exporters each sector's reference point
  (`Sector.reference_latitude`, `reference_longitude`) instead of plot coordinates.
- **DB constraints back up validation:** Rwanda bounding box and area range on plots, the weight
  range on deliveries, one active price schedule per effective date globally across season labels,
  one price per grade per schedule, and `client_reference` unique per station. Global cross-season
  effective-date precedence is a project assumption; the F1, F2, and Summative contracts do not
  specify it.
- **Idempotency (farmers, plots and deliveries):** a replay is detected before validation, so a
  retry returns the original even if prices have changed since. The replayed body must match the
  original, otherwise the response is `409`. All three resources share one implementation, `NaturalKeyReplayMixin` in
  `apps/core/idempotency.py`, so the 409 body is identical everywhere. A race between two identical requests is caught by the
  unique constraint and also returns the original.
- **Personal data:** since F2, `national_id` is returned only to field agents, masked to its last
  four digits, and is absent for exporters and auditors. **Known limitation:** `phone` and farmer
  names are still visible to all three roles; masking phones is deferred (see DECISION_LOG.md).

## Development history

The F1 history has one unusual stretch, recorded here so it reads clearly:

| Commit | What happened |
|---|---|
| `8d262ce`…`a0bc3af` | The F1 implementation, built up in small commits: bootstrap, models, endpoints, async task, feed tests, schema and CI, ADR and README, then hardening. |
| `5e1c6eb` | The implementation was removed, with the intent of rewriting it independently. |
| `132c56e` | The rewrite was not completed, so the implementation was restored in one commit, together with the changes from a Claude-assisted review: one shared idempotency mixin for all creates (ADR-003), indexes for the farmer and plot list cursors with `EXPLAIN` tests, and the risk-check backlog on `/api/status/`. |

**F1 feedback:** the Classroom 50 Feedback pull request (#1) had no teacher comments or reviews
when F2 started, and F1 autograding scored 100/100 (`aa58d56`), so there were no review points to
address.

**F2** was built in nine steps, one commit each, committed directly to `main` (not through
branches and pull requests, as an earlier version of this README planned). Before each commit,
`make check` (lint, format, types, Django check, migration check, tests, schema freshness) passed
locally:

| Commit | Step |
|---|---|
| `ec43c22` | Widen the southern latitude bound to -2.95 so fixture plot M2 is accepted |
| `ec1bc61` | `UserProfile` (role + station) and the central deny-by-default `ROLE_POLICIES` |
| `6469e72` | Session + token authentication, the two login endpoints, `IsAuthenticated` by default |
| `b2f684b` | `seed_rbac_fixtures` |
| `acc05db` | Enforce the policies: permission class and `visible_to()` station scoping |
| `f9522a7` | Sector reference points for exporter coarsening |
| `555ea41` | Field rules: national-ID masking, coordinate coarsening, commercial terms |
| `0a2fe7b` | Append-only `AuditLog` and `/api/audit-log/` |
| *(this commit)* | Documentation (`docs/RBAC_MATRIX.md`, DECISION_LOG.md completion, README), audit-log precision filters, and a test that every serializer applies the field rules |

## AI-use disclosure

### F1

Used for: Reviewing the F1 submission against the rubric, identifying potential improvements, debugging assistance, and documentation formatting. Claude also provided suggestions for the follow-up implementation and testing work.
My role: I reviewed, implemented, and explained the changes myself, including the idempotency handling, database indexes, risk-check status endpoint, tests, README updates, and ADR reasoning.
Verification: I verified the changes with the full pytest suite, ruff check, mypy, manage.py makemigrations --check, and a regenerated and validated schema.yml. The database index claims were also confirmed with EXPLAIN on a migrated database.
Disclosure: The F1 commits that received Claude assistance include a Co-Authored-By: Claude trailer, except `132c56e`, whose commit message names the Claude-assisted review instead.


### F2 AI-Use Annex

**Tool:** Claude Code (Anthropic's Claude, Opus model), working in this repository.

**What Claude did:**

- Analysed the F1 codebase against the F2 contract and identified implementation questions, including the fixture plot M2 latitude issue, the seed farmer's national-ID collision with the F1 flow, anonymous F1 tests, and treatment of the price schedule.
- Assisted with implementation of the nine F2 steps, including code, migrations, tests, and documentation updates.
- Provided debugging assistance and helped identify implementation issues during development.
- Assisted with formatting and documenting the F2 README sections.

**My role and decisions:**

- I made the final design and trade-off decisions for F2 and authored and reviewed the Decision Log.
- I decided to widen the latitude bound through a migration, identify the seed farmer using national ID and member number, keep the price schedule public, make exporters and auditors read-only, and scope field-agent farmer visibility through plots.
- When Claude identified that newly registered farmers could be invisible to their own field agent, I decided to add the home station to the visibility rule.
- I reviewed, implemented, and verified the resulting changes rather than treating Claude's suggestions as automatically correct.

**My verification:**

- I ran `make check` myself before every commit.
- I ran `migrate` and `seed_rbac_fixtures` twice locally to verify that the seed command is idempotent.
- I asked for internal implementation notes to be removed from the published OpenAPI schema and reviewed the resulting documentation.
- I made every commit and push myself; Claude made no commits or pushes.

**Disclosure:**

All F2 commits were produced with Claude's assistance. The eight commits `ec43c22` to `0a2fe7b` do not carry a `Co-Authored-By` trailer, unlike the F1 commits. Their messages were drafted without one. This was an oversight, not an attempt to conceal AI assistance. The subsequent documentation commit carries the trailer.

### Summative assistance record

OpenAI Codex assisted in this local Summative hardening session. It updated factual bug,
deployment, performance, and ADR descriptions; corrected payment and sector-reference wording;
added regression coverage for auditor delivery metadata, JSON logging, and broker-credential
redaction; added a reproducible local feed benchmark and HTTP smoke check; and ran local
validation commands. It made narrow factual wording corrections in `DECISION_LOG.md` without
supplying personal reasoning. It made no Git history changes and performed no deployment. The student
should review these changes and remains responsible for personal trade-off reasoning and the oral
defense.

