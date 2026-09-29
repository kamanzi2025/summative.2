# Kawa Network API

Backend for the Kawa Network coffee cooperative. It registers farmers and their plots, records
cherry deliveries at washing stations (starting with Nyaruguru), pays farmers from the active
season's price schedule, and checks every plot against an external deforestation-risk registry
**in the background**, so a slow or broken registry never stops a farmer being paid.

This is the Formative 1 (F1) milestone of the `2793` Advanced Python assessment. The same
repository continues into F2 (auth, RBAC, location privacy) and the Summative.

- **Architecture decisions:** [ADR.md](ADR.md)
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
7. [API reference with curl examples](#api-reference-with-curl-examples)
8. [Performance: the station delivery feed](#performance-the-station-delivery-feed)
9. [Design notes](#design-notes)
10. [AI-use disclosure](#ai-use-disclosure)

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
| `apps/pricing/` | `PriceSchedule` / `PriceEntry` (one active schedule per season), `/api/price-schedule/` |
| `apps/deliveries/` | `Delivery` (plot-linked, price and risk snapshots, idempotency key), station feed |
| `tests/` | pytest suite, including a mirror of the F1 contract's exact payloads |

Views are thin. Validation lives in serializers (field and cross-field `validate()`), and
business operations live in each app's `services.py`, which both views and Celery tasks call.

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
python manage.py migrate             # also seeds sectors, stations and the 2026A price schedule
python manage.py seed_demo           # optional: demo farmers, plots and deliveries (idempotent)
python manage.py runserver
```

Then open <http://127.0.0.1:8000/api/docs/> for Swagger UI.

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
| `REGISTRY_API_URL` | *(empty)* | Real registry endpoint. Empty means the simulated registry (the only client in F1). |
| `REGISTRY_API_TIMEOUT` | `30` | Seconds before a registry call counts as a `timeout` attempt |
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

```bash
python -m pytest -q                                   # 90 tests
ruff check .                                          # lint
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

CI (`.github/workflows/ci.yml`) runs ruff, mypy, `check`, the migration check, schema freshness and
pytest on every push to `main`.

## API reference with curl examples

Base URL: `http://127.0.0.1:8000`. All bodies are JSON. Money and weights are **decimal strings**,
never floats.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status/` | Liveness |
| POST, GET | `/api/farmers/` | Register / list farmers |
| GET | `/api/farmers/{id}/` | One farmer |
| POST, GET | `/api/plots/` | Register a plot (async risk check) / list with filters |
| GET | `/api/plots/{id}/` | One plot |
| GET | `/api/plots/{id}/risk-checks/` | Registry attempt history for a plot |
| POST, GET | `/api/deliveries/` | Record a delivery (idempotent) / delivery feed |
| GET | `/api/deliveries/{id}/` | One delivery |
| GET | `/api/stations/`, `/api/stations/{id}/` | Washing stations |
| GET | `/api/stations/{id}/deliveries/` | One station's delivery feed |
| GET | `/api/price-schedule/` | Active season's per-grade prices |
| GET | `/api/schema/`, `/api/docs/` | OpenAPI schema, Swagger UI |

### Status

```bash
curl -s http://127.0.0.1:8000/api/status/
```
```json
{"status": "ok", "service": "kawa-api", "time": "2026-09-29T18:30:22.786299Z"}
```

### Register a farmer

Phones are accepted as `+2507XXXXXXXX`, `2507XXXXXXXX` or `07XXXXXXXX` (MTN/Airtel) and stored in
E.164. `national_id` is optional but, when present, must be 16 digits and unique.

```bash
curl -s -X POST http://127.0.0.1:8000/api/farmers/ -H 'Content-Type: application/json' -d '{
  "full_name": "Uwimana Béatrice", "member_number": "KWA-F-0417", "cooperative": "Huye",
  "national_id": "1198770123456789", "phone": "+250780000000"}'
```
```json
{"id": 4, "full_name": "Uwimana Béatrice", "member_number": "KWA-F-0417", "cooperative": "Huye",
 "phone": "+250780000000", "national_id": "1198770123456789", "home_station": null,
 "created_at": "2026-09-29T20:30:22.817202+02:00"}
```

### Register a plot (returns immediately, check runs in background)

`sector` and `washing_station` are given by name. Coordinates must fall inside Rwanda, and the area
must be between 0 and 50 ha.

```bash
curl -s -X POST http://127.0.0.1:8000/api/plots/ -H 'Content-Type: application/json' -d '{
  "farmer": 4, "plot_code": "KWA-P-0417-A", "sector": "Kigoma", "washing_station": "Nyaruguru",
  "latitude": "-2.540000", "longitude": "29.710000", "area_hectares": "0.42"}'
```
```json
{"id": 6, "farmer": 4, "plot_code": "KWA-P-0417-A", "label": "", "sector": "Kigoma",
 "washing_station": "Nyaruguru", "latitude": "-2.540000", "longitude": "29.710000",
 "area_hectares": "0.4200", "risk_status": "pending", "risk_checked_at": null,
 "requires_manual_review": false, "created_at": "2026-09-29T20:31:35.170000+02:00"}
```

### List plots (filters: `farmer`, `sector`, `washing_station`, `risk_status`, `requires_manual_review`)

`GET /api/plots/?requires_manual_review=true` is compliance's review queue: plots still
`unverified` after `RISK_CHECK_MANUAL_REVIEW_DAYS`.

```bash
curl -s 'http://127.0.0.1:8000/api/plots/?risk_status=pending&page_size=1'
```
```json
{"next": "http://127.0.0.1:8000/api/plots/?cursor=cD0yMDI2LTA5LTI5KzE4JTNBMzMlM0ExMS42Nzg0OTIlMkIwMCUzQTAw&page_size=1&risk_status=pending",
 "previous": null,
 "results": [{"id": 11, "farmer": 4, "plot_code": "KWA-P-DOWN-1", "sector": "Kigoma",
              "washing_station": "Nyaruguru", "risk_status": "pending", "...": "..."}]}
```

### Risk-check history

```bash
curl -s http://127.0.0.1:8000/api/plots/11/risk-checks/
```
```json
[{"attempt_number": 1, "outcome": "error", "started_at": "2026-09-29T20:33:12.72+02:00",
  "finished_at": "2026-09-29T20:33:12.88+02:00", "duration_ms": 166,
  "error_message": "registry returned 503 Service Unavailable", "task_id": "f5822d6a-..."},
 {"attempt_number": 2, "outcome": "error", "...": "..."}]
```

### Record a delivery

The station must be the plot's station. `delivered_on` defaults to today and cannot be in the
future. The price comes from the active schedule **at recording time** and is snapshotted.
`client_reference` is the phone's idempotency key (optional, unique per station).

```bash
curl -s -i -X POST http://127.0.0.1:8000/api/deliveries/ -H 'Content-Type: application/json' -d '{
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
  "message": "client_reference 'nyr-phone-02-0040' was already used for delivery 46 with different values.",
  "details": {"delivery_id": 46, "mismatched_fields": ["weight_kg"]}}}
```

### Error responses

Every error uses one envelope: `{"error": {"code", "message", "details"}}`.

```bash
curl -s -X POST http://127.0.0.1:8000/api/deliveries/ -H 'Content-Type: application/json' \
  -d '{"plot": 1, "washing_station": "Kamonyi", "weight_kg": "-3", "grade": "A", "delivered_on": "2030-01-01"}'
```
```json
{"error": {"code": "validation_error", "message": "The request data is invalid.",
  "details": {"weight_kg": ["Must be greater than 0."],
              "delivered_on": ["Delivery date cannot be in the future."]}}}
```

Once the field errors are fixed, cross-field rules run:

```json
{"error": {"code": "validation_error", "message": "The request data is invalid.",
  "details": {"washing_station": ["Plot KWA-P-DEMO-01 delivers to Nyaruguru, not Kamonyi."]}}}
```

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | Field or cross-field rule failed (`details` maps field → messages) |
| 400 | `parse_error` | Malformed JSON |
| 404 | `not_found` | Unknown id or route, e.g. `{"error": {"code": "not_found", "message": "No Farmer matches the given query.", "details": {}}}` |
| 405 | `method_not_allowed` | e.g. `DELETE /api/price-schedule/` |
| 409 | `conflict` | A `client_reference` was reused with a different body (`details.mismatched_fields`), or two requests raced past validation into a DB uniqueness constraint |
| 500 | `server_error` | Unexpected failure. The traceback is logged, never returned. |

Why duplicates are **400**, not 409: a duplicate phone, member number or plot code that validation
can see is reported against the specific field, so the phone app can highlight it. A **409** is
reserved for real conflicts with existing data: the rare race where the database constraint, not
the serializer, catches a duplicate, and a `client_reference` reused with different values. An
identical resend under the same `client_reference` is neither: it is an idempotent replay (`200`).

### Station delivery feed (cursor-paginated)

`GET /api/deliveries/` and `GET /api/stations/{id}/deliveries/` return the same slim rows, newest
first. Filters: `washing_station` (name, on `/api/deliveries/`), `grade`, `risk_status` (the plot's
*current* status), `exportable` (`true`/`false`), and `since` (ISO datetime, strictly newer than
`recorded_at`). Compliance's review list of paid-but-flagged cherry is
`?exportable=false&risk_status=flagged`. Use `page_size`
to change the page length (default 20, maximum 100).

```bash
curl -s 'http://127.0.0.1:8000/api/stations/1/deliveries/?page_size=2'
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
60 seconds** (`PRICE_SCHEDULE_MAX_AGE_SECONDS`). Delivery pricing never uses a cached value; it is
read from the database when each delivery is recorded.

## Performance: the station delivery feed

**Assessed feature: cursor pagination of the station delivery feed.** The full reasoning is in
[ADR-002](ADR.md#adr-002-whose-performance-problem-to-solve-first-the-station-delivery-feed).

- **Why cursor, not offset.** During the harvest peak, Nyaruguru records about 400 deliveries a
  day, and they land at the top of the feed while Emmanuel is scrolling. With `?page=2` (offset),
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
- **No N+1.** `select_related("plot__farmer", "washing_station")` makes each page **one SQL query**
  (two for the station route, including the station lookup that returns 404). Tests assert this
  with `django_assert_num_queries`.
- **No `COUNT(*)`.** Cursor pagination does not count the table, unlike page-number pagination.
- **Small payloads for 2G.** The feed serializer is flat (no nested plot or farmer objects).
  **Measured:** one page of 20 deliveries is **6,316 bytes** (about 315 bytes per row). With
  `GZipMiddleware` it travels as **832 bytes**.
- **Incremental sync.** `?since=` lets the phone download only rows newer than the newest one it
  has.

## Design notes

See **[ADR.md](ADR.md)** for:

- **ADR-001, accept-then-verify:** why the deforestation-risk check is an asynchronous, retried
  status on the plot, why deliveries are never blocked by it, and the policy for plots whose check
  never succeeds (deliveries accepted and paid, snapshotted, non-exportable until `clear`, flagged
  deliveries surfaced for review, manual review after 7 days `unverified`).
- **ADR-002:** why Emmanuel's feed was optimised before the pricing path.

Other decisions worth knowing:

- **A delivery references a plot, not a farmer.** The farmer is reached through the plot, which
  keeps the provenance chain export lot → delivery → plot → land intact.
- **Snapshots:** `unit_price_rwf`, `amount_due_rwf` and `plot_risk_status_at_delivery` are copied
  onto the delivery, so later price changes or risk verdicts never rewrite history.
  `is_exportable` is computed from the plot's *current* status.
- **Sectors and stations are models**, referenced by name in the API. Formative 2 scopes access by
  washing station and coarsens coordinates by sector.
- **DB constraints back up validation:** Rwanda bounding box and area range on plots, the weight
  range on deliveries, one active price schedule per season, one price per grade per schedule, and
  `client_reference` unique per station.
- **Idempotency:** a replay is detected before validation, so a retry returns the original even if
  prices have changed since. The replayed body must match the original (plot, weight, grade and
  date), otherwise the response is `409`. A race between two identical requests is caught by the
  unique constraint and also returns the original.
- **Personal data (known F1 limitation):** `national_id` and `phone` are returned in full because
  F1 has no authentication yet. Formative 2 adds roles, masks national IDs to their last four
  digits for field agents, and hides them from exporters and auditors (see `F2_CONTRACT.md`).

## AI-use disclosure

- **Tool:** Claude Code (Anthropic's Claude).
- **What I asked it to help with:** scaffolding the Django project and apps from my design brief
  (domain model, endpoints, validation rules, async risk-check policy, cursor-paginated feed),
  writing the test suite, and drafting the ADR and README.
- **What I changed or verified before accepting:** *(to be completed by the student)*
- **What I can explain independently:** *(to be completed by the student)*
