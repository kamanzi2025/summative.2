# Deployment and Operations

This document describes the runtime paths present in this repository. The default Dockerfile
target and Compose profile are for local development and coursework verification. An explicit
Dockerfile `production` target runs Gunicorn with the existing Django WSGI application. It is a
minimal production-style process command, not a complete or verified production deployment. TLS
termination, static-file serving, migration ownership, health checks, and an operating environment
still require operator configuration and validation.

## Prerequisites

- Python 3.11 or newer (the container uses Python 3.12).
- Redis 7 for asynchronous risk checks and the periodic retry sweep.
- SQLite for a single-machine development run. PostgreSQL is supported through `DATABASE_URL` and
  the installed psycopg driver.
- Docker Compose is optional if Python and Redis are run separately.

Install the pinned-range dependencies from the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` for local use. Do not put real credentials in source control. The
settings loader reads `.env` from the repository root; environment variables supplied by the
runtime take precedence.

Set these values for a non-local deployment:

```dotenv
SECRET_KEY=replace-with-a-private-random-secret
DEBUG=False
ALLOWED_HOSTS=api.example.invalid
DJANGO_ENV=production
CSRF_TRUSTED_ORIGINS=https://api.example.invalid
DATABASE_URL=postgres://USER:PASSWORD@DATABASE_HOST:5432/kawa
CELERY_BROKER_URL=redis://REDIS_HOST:6379/0
CELERY_RESULT_BACKEND=redis://REDIS_HOST:6379/0
```

The example host and credentials above are placeholders, not working infrastructure. Protect the
secret key and database credentials using the environment's secret facility. With
`DJANGO_ENV=production`, startup rejects a missing, short, or known placeholder secret, `DEBUG=True`,
an omitted/empty/wildcard `ALLOWED_HOSTS`, and non-HTTPS CSRF trusted origins. These checks do not
prove that a supplied secret has sufficient randomness or that hostnames are owned by the operator.
The database URL must be provided by the operator when using PostgreSQL; the repository does not
provision a database server.

Production mode sets secure session and CSRF cookies and redirects HTTP requests to HTTPS. It trusts
only `X-Forwarded-Proto: https` for detecting TLS termination. The loopback publication in the
container command below is for a trusted proxy running on the same host. The proxy must remove any
client-supplied `X-Forwarded-Proto` and write its own value; never forward a client-provided value
unchanged. For a proxy in another container, attach both services to a private container network
and do not publish the Gunicorn port on the host. Do not expose the Gunicorn port directly to clients.
`CSRF_TRUSTED_ORIGINS` is optional for same-origin browser requests and should list only actual
HTTPS origins when cross-origin browser requests are required. HSTS remains disabled by default;
configure `SECURE_HSTS_SECONDS` only after verifying the public TLS hostname and its subdomains.

Additional settings supported by `config/settings.py` include:

| Variable | Purpose |
|---|---|
| `DJANGO_ENV` | `development` by default; `production` enables startup validation and proxy-aware HTTPS settings. |
| `CSRF_TRUSTED_ORIGINS` | Optional comma-separated browser origins; production entries must be HTTPS origins. |
| `SECURE_HSTS_SECONDS` | Production HSTS duration in seconds; defaults to `0` until the public TLS setup is verified. |
| `CELERY_TASK_ALWAYS_EAGER` | Runs tasks inline when `True`; keep `False` for the worker flow. |
| `CELERY_BROKER_TRANSPORT_OPTIONS` | Optional JSON transport options for Celery. |
| `REGISTRY_API_URL` | Empty selects the simulator. A real registry URL can only be used after its request and response contract is confirmed; see below. |
| `REGISTRY_API_TIMEOUT` | Simulator call timeout in seconds; real registry requests are not yet supported. |
| `RISK_REGISTRY_MIN_LATENCY`, `RISK_REGISTRY_MAX_LATENCY` | Simulator latency range. |
| `RISK_REGISTRY_FAILURE_RATE`, `RISK_REGISTRY_FLAG_RATE` | Simulator failure and flag probabilities. |
| `RISK_CHECK_MAX_RETRIES`, `RISK_CHECK_BACKOFF_SECONDS` | Retry count and backoff base. |
| `RISK_CHECK_STALE_HOURS`, `RISK_CHECK_MANUAL_REVIEW_DAYS`, `RISK_CHECK_SWEEP_MINUTES` | Retry sweep and manual-review thresholds. |
| `PRICE_SCHEDULE_MAX_AGE_SECONDS` | Public price response cache lifetime. |
| `LOG_LEVEL` | Application log level. |

### Registry integration

With `REGISTRY_API_URL` empty, the application uses the simulated registry. The repository does
not document the real registry's HTTP method, request fields, authentication, or response schema.
While that contract is unknown, a non-empty URL fails closed and records an unavailable attempt;
the application makes no HTTP request and does not fall back to a simulated clearance. Risk checks
run in Celery; delivery recording does not wait for the registry.

## Database setup and migrations

For a local database, create `.env` and run:

```sh
python manage.py migrate --noinput
python manage.py seed_rbac_fixtures
```

Migrations create the schema and seed reference sectors, washing stations, and a placeholder price
schedule. `seed_rbac_fixtures` creates published coursework test credentials and fixture records;
do not run that command against a production database.

Before deploying a new version, review pending migrations and take a database backup using the
database operator's established procedure. Then apply migrations as a deliberate release step:

```sh
python manage.py migrate --noinput
```

The Compose `web` service runs this command automatically at container startup. That behavior is
convenient for local development; production migration ownership and rollback procedures are not
specified in this repository and require operator confirmation. No migration is run by this
document or by the test commands.

The pricing migration allows more than one active schedule per season when effective dates differ.
Reversing it after such schedules have been recorded may fail under the previous one-active-schedule
constraint. Review active schedules and prepare a data reconciliation before attempting that
rollback.

## Start the application and workers

### Local Python processes

Start Redis (for example, `docker compose up -d redis`), then use separate terminals with the
virtual environment activated:

```sh
python manage.py runserver 0.0.0.0:8000
celery -A config worker -l info
celery -A config beat -l info
```

`runserver` is Django's development server. The explicit Dockerfile `production` target provides a
Gunicorn WSGI command; it does not change these local Python development commands.

### Docker Compose development profile

```sh
docker compose --profile app up --build
```

The profile runs web, Celery worker, Celery beat, and Redis containers. It stores SQLite data in
the `db-data` named volume. The `web` container applies migrations at startup. The profile uses
`runserver` and the example database, so it is for local development rather than production. The
default Dockerfile target is also `development`, preserving this Compose behavior.

### Explicit Gunicorn container target

The `production` build target uses Gunicorn to serve `config.wsgi:application`. Build and run that
target explicitly:

```sh
docker build --target production -t kawa-network:production .
docker run --rm -p 127.0.0.1:8000:8000 --env-file /path/to/runtime.env kawa-network:production
```

Supply `/path/to/runtime.env` from the runtime environment; do not copy real secrets into the image
or repository. The production image entrypoint forces `DJANGO_ENV=production` before starting the
requested process, even if the env file contains `DJANGO_ENV=development` or omits the variable.
The image command is equivalent to:

```sh
gunicorn --bind 0.0.0.0:8000 config.wsgi:application
```

This target does not run migrations automatically. The shown container command is an application
process example, not a complete production deployment recipe: this repository does not configure
TLS termination, PostgreSQL, worker/beat orchestration, health checks, or migration ownership. The
target has not been verified in Docker or against PostgreSQL in this environment.

### Production static files (serving incomplete)

Django defines `STATIC_ROOT=/app/staticfiles`, and this command collects assets into a named volume:

```sh
docker volume create kawa-static
docker run --rm --env-file /path/to/runtime.env \
  --mount source=kawa-static,target=/app/staticfiles \
  kawa-network:production python manage.py collectstatic --noinput
```

This only performs collection. Gunicorn does not serve the collected files. Static serving remains
incomplete: the repository has no reverse-proxy configuration or service, no wiring that mounts
`kawa-static` into a proxy, and no verified `/static/` route. A future proxy setup must mount this
volume read-only at its static document root and configure a matching route (for example, Nginx
could use `alias /usr/share/nginx/html/static/;`). It must also terminate TLS and overwrite
`X-Forwarded-Proto` before forwarding API traffic. These steps have not been run or verified in
Docker; do not treat static assets as served until that proxy configuration and volume wiring exist
and are tested.

### Reproducible local web smoke check

From a fresh local checkout, install the declared dependencies as above, then run this isolated
HTTP smoke test from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 DATABASE_URL=sqlite:///:memory: .venv/bin/python -m pytest -p no:cacheprovider -q -s local_checks/smoke/test_deployment_smoke.py
```

Pytest creates and migrates its temporary test database, starts Django's test HTTP server on
loopback, and requests the public `/api/status/` route. The `DATABASE_URL` override prevents the
project's local `.env` or default database path from being used. This check does not start Redis,
Celery worker/beat, or the Compose containers; it verifies the Django web process and status route
only. It needs permission to bind a loopback port. If local security settings reject that bind, the
failure is an environment restriction, not a health-route result.

In the latest recorded local run, the command completed with **1 passed in 2.01s**. Docker is not
installed in this environment (`docker --version` returned `command not found`), so no container
build or Compose startup was tested. This smoke result is not production deployment evidence.

## Health checks and troubleshooting

Check the public status endpoint:

```sh
curl -fsS http://127.0.0.1:8000/api/status/
```

The response includes risk-check backlog counts. This is a database-dependent status endpoint:
it queries the database to produce those counts, so `status: "ok"` means the request and backlog
query succeeded. A registry, Redis, broker, or worker outage does not directly change the status
field. `risk_checks.healthy` only reports whether plots have exceeded the stale-check threshold;
it does not ping Redis or prove a worker is connected. A dead worker may only become visible after
an outstanding plot becomes stale. Treat this as an application/backlog signal, not a complete
readiness check for the API, database, broker, and worker together. Check Redis and Celery through
separate operator monitoring. A registry outage is retried and does not block delivery recording.

Common checks:

- If the web service cannot connect to the database, verify `DATABASE_URL` and database
  availability. Compose uses its configured SQLite volume and ignores a local SQLite path.
- If risk-check attempts do not progress, verify `CELERY_BROKER_URL`, Redis health, and worker
  logs. Verify Celery beat is running if stale plots are not being requeued.
- Inspect `GET /api/plots/{id}/risk-checks/` with an authorized user for recorded outcomes and
  error messages. Registry responses and credentials should not be copied into logs or reports.
- If `/api/status/` returns an error, check application logs and database connectivity. The
  endpoint reads backlog data from the database, so it is not a database-independent probe.

## Safe operation and limitations

- Set `DEBUG=False`, a private `SECRET_KEY`, and a narrow `ALLOWED_HOSTS` list outside local
  development. Put the API behind an operator-managed HTTPS endpoint before sending credentials.
- Keep the Celery broker and database private to the application environment. Use separately
  managed backups and test restore procedures before relying on delivery or audit records.
- Do not use the public-password RBAC fixture accounts outside coursework. Change or remove them
  before any environment containing real data.
- The default Dockerfile target launches `runserver`; the explicit `production` target launches
  Gunicorn. TLS setup, static-file serving, monitoring, and a deployment platform are not
  configured here.
- A real registry integration remains unverified until its HTTP contract, authentication method,
  and response fields are supplied and implemented. The local simulator is the supported default.
- This project has no documented production migration rollback procedure or production readiness
  runbook. Confirm these with the deployment operator before a production release.
