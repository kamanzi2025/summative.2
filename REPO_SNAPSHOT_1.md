<!-- REPO_SNAPSHOT part 1 of 4. Paste all parts in order. -->

# REPO SNAPSHOT: advanced-python-programming-kawa-kamanzi2025

Generated 2026-10-15 from a fresh clone of `https://github.com/ALU-BSE/advanced-python-programming-kawa-kamanzi2025.git`, on branch `main` at `5ab0823`.
The repo was not modified. Commands ran with a temporary venv, a temporary SQLite DB (`DATABASE_URL` pointed outside the repo), `PYTHONDONTWRITEBYTECODE=1` and `pytest -p no:cacheprovider`.
Redactions: the `SECRET_KEY` default/example values and credentials in example database URLs are replaced with `<REDACTED>`. No real secrets were found. The fixture password `GraderPass123!` and throwaway test-only passwords (e.g. `"x"`) are left as they are.

## 1. CONTEXT

### git log --oneline -40

```text
5ab0823 Accept Bearer and Basic logins; keep F1 registrations open without a login while every read stays 401
dc05989 Give logged-in users without a role the F1 operations under the most restrictive field rules; keep hidden writable fields accepted on input
283fcbe Fix F2 grading failures: national ID not unique so the F1 flow works after seeding; sector reference points that no rounding reaches
ee7127e Complete F2 docs: RBAC matrix, decision log, README; audit precision filters; serializer field-rule guard
0a2fe7b Add append-only AuditLog: one row per protected request, auditor-only /api/audit-log/
555ea41 Apply field rules by role: mask national IDs, coarsen exporter coordinates, hide commercial terms from auditors
f9522a7 Add sector reference points for exporter coordinate coarsening; keep internal notes out of schema.yml
acc05db Enforce ROLE_POLICIES: role permission class and station scoping on querysets, sub-routes, replays and writes
b2f684b Add idempotent seed_rbac_fixtures command for the F2 role users, seed farmer, plots and deliveries
6469e72 Require authentication: session + token auth, staff-login and api-token endpoints, role test fixtures
ec1bc61 Add user profiles with role and station, and central deny-by-default ROLE_POLICIES
ec43c22 Widen southern latitude bound to -2.95 so F2 fixture plot M2 is accepted
d2ca89a Revise AI-use disclosure in README
aa58d56 Document development history, correct AI disclosure, add format gate and make check
38b0cc2 Add ADR index and ADR-003 on idempotent writes
132c56e Restore F1 implementation with Claude-assisted review changes
5e1c6eb Remove AI-generated F1 implementation; rewriting my own solution
a0bc3af Make farmer and plot registration idempotent on their natural keys
b0c08a0 Complete AI-use disclosure
611144f Allow the testserver host so the autograder's test client is accepted
5780ce6 Align ADR stakeholder reasoning with the F1 brief
ce56216 Update schema, ADR and README for hardening changes
c42b049 Add mypy with django and DRF stubs to tooling and CI
6b30bbd Add compliance review queues and prove the feed index is used
993be08 Reject idempotency-key reuse with a different body (409)
6481bf2 Harden risk-check task: capped backoff, time limits, unique attempts
c820ce0 Add ADR and README
0d1ed77 Add generated OpenAPI schema and CI lint/test job
c8222ea Add tests for the cursor-paginated station delivery feed
53098ca Add Celery risk-check task with attempt logging and stale sweeper
73e54f4 Add farmer, plot, delivery and price-schedule endpoints with validation
dd7314e Add domain models, migrations and seeded reference data
8d262ce Bootstrap Django project with env-driven settings and shared API core
57600e0 [Classroom 50] Open Feedback PR (gh student accept)
b5bcf28 [Classroom 50] Initialize .classroom50.yaml and autograde workflow (gh student accept)
67dfa40 Initial commit
```

### git branch -a

```text
* main
  remotes/origin/HEAD -> origin/main
  remotes/origin/feedback
  remotes/origin/main
  remotes/origin/summative/seed
```

### git tag

```text
f1
f2
submit/2026-09-29T19-25-34Z-5780ce6
submit/2026-09-29T19-32-46Z-b0c08a0
submit/2026-09-29T20-20-15Z-132c56e
submit/2026-09-29T20-29-54Z-aa58d56
submit/2026-10-04T19-54-48Z-ee7127e
submit/2026-10-04T20-30-12Z-283fcbe
submit/2026-10-04T20-52-56Z-dc05989
submit/2026-10-04T21-17-00Z-5ab0823
```

### Versions

- Python: 3.12 (`pyproject.toml`: ruff target py311, mypy python_version 3.12; Dockerfile `python:3.12-slim`). Local run used Python 3.12.3.
- `requirements.txt` ranges: `Django>=5.0,<5.2`, `djangorestframework>=3.15,<3.16`, `celery>=5.4,<5.5`, `drf-spectacular>=0.28,<0.29`, `django-filter>=24.3,<26`.
- Resolved when installed for this snapshot:

```text
celery==5.4.0
Django==5.1.15
django-filter==25.1
djangorestframework==3.15.2
drf-spectacular==0.28.0
pytest==8.4.2
pytest-django==4.14.0
```

### summative/seed branch

- Local branch: **no**. Remote branch: **yes**, `origin/summative/seed` at `eeffead` ("Add summative/seed seed (4 file(s))").
- Merged into main: **NO**. It is one commit on top of `main`'s HEAD (`5ab0823`) and adds:

```text
 tests/staging/conftest.py                          | 33 ++++++++
 .../staging/test_delivery_risk_check_stranding.py  | 70 +++++++++++++++++
 tests/staging/test_pagination_coarsening.py        | 90 ++++++++++++++++++++++
 tests/staging/test_price_schedule_staleness.py     | 40 ++++++++++
 4 files changed, 233 insertions(+)
```

## 2. PROJECT TREE

`main` working tree. Excludes .git, venvs, `__pycache__`, node_modules and staticfiles. Migration files are listed by name only. `tests/staging/` exists only on `origin/summative/seed`.

```text
advanced-python-programming-kawa-kamanzi2025/
├── .classroom50.yaml
├── .dockerignore
├── .env.example
├── .github/
│   ├── pull_request_template.md
│   └── workflows/
│       ├── autograde.yaml
│       └── ci.yml
├── .gitignore
├── ADR.md
├── DECISION_LOG.md
├── Dockerfile
├── Makefile
├── README.md
├── apps/
│   ├── __init__.py
│   ├── accounts/
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── authentication.py
│   │   ├── field_rules.py
│   │   ├── management/
│   │   │   ├── __init__.py
│   │   │   └── commands/
│   │   │       ├── __init__.py
│   │   │       └── seed_rbac_fixtures.py
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py
│   │   │   └── __init__.py
│   │   ├── models.py
│   │   ├── permissions.py
│   │   ├── policies.py
│   │   ├── scoping.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── audit/
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── filters.py
│   │   ├── middleware.py
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py
│   │   │   └── __init__.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── exceptions.py
│   │   ├── idempotency.py
│   │   ├── logging.py
│   │   ├── management/
│   │   │   ├── __init__.py
│   │   │   └── commands/
│   │   │       ├── __init__.py
│   │   │       └── seed_demo.py
│   │   ├── pagination.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── deliveries/
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── filters.py
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py
│   │   │   └── __init__.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── services.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── pricing/
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py
│   │   │   ├── 0002_seed_price_schedule.py
│   │   │   └── __init__.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── services.py
│   │   ├── urls.py
│   │   └── views.py
│   └── registry/
│       ├── __init__.py
│       ├── admin.py
│       ├── apps.py
│       ├── clients.py
│       ├── filters.py
│       ├── migrations/
│       │   ├── 0001_initial.py
│       │   ├── 0002_seed_reference_data.py
│       │   ├── 0003_unique_attempt_number.py
│       │   ├── 0004_list_cursor_indexes.py
│       │   ├── 0005_widen_rwanda_lat_min.py
│       │   ├── 0006_sector_centroid.py
│       │   ├── 0007_seed_sector_centroids.py
│       │   ├── 0008_sector_centroid_required.py
│       │   ├── 0009_national_id_not_unique.py
│       │   ├── 0010_sector_reference_point.py
│       │   └── __init__.py
│       ├── models.py
│       ├── serializers.py
│       ├── services.py
│       ├── tasks.py
│       ├── urls.py
│       ├── validators.py
│       └── views.py
├── config/
│   ├── __init__.py
│   ├── asgi.py
│   ├── celery.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── docker-compose.yml
├── docs/
│   ├── RBAC_MATRIX.md
│   ├── autograding/
│   │   ├── F1_CONTRACT.md
│   │   ├── F2_CONTRACT.md
│   │   ├── RUN_CONTRACT.md
│   │   └── SUMMATIVE_CONTRACT.md
│   └── templates/
│       ├── ADR_TEMPLATE.md
│       ├── BUG_REPORT_TEMPLATE.md
│       ├── DECISION_LOG_TEMPLATE.md
│       └── RBAC_MATRIX_TEMPLATE.md
├── manage.py
├── pyproject.toml
├── requirements.txt
├── schema.yml
└── tests/
    ├── conftest.py
    ├── test_access_scoping.py
    ├── test_audit_log.py
    ├── test_auth.py
    ├── test_contract.py
    ├── test_deliveries.py
    ├── test_farmers.py
    ├── test_feed.py
    ├── test_field_rules.py
    ├── test_grader_smoke.py
    ├── test_plots.py
    ├── test_pricing_and_errors.py
    ├── test_risk_checks.py
    ├── test_role_policies.py
    ├── test_sector_reference_points.py
    └── test_seed_rbac_fixtures.py
```

## 3. FILE CONTENTS

Every non-empty, non-migration Python file under `config/` and `apps/` is included below. That covers settings, all urls/models/serializers/views/permissions, RBAC, masking, coarsening, audit, Celery and risk-check code, pricing, and both management commands. Empty `__init__.py` files are omitted.

### config/__init__.py

```python
from .celery import app as celery_app

__all__ = ("celery_app",)
```

### config/asgi.py

```python
"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
```

### config/celery.py

```python
"""Celery application for background work (deforestation-risk checks)."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

### config/settings.py

```python
"""Django settings for the Kawa Network API.

Every deploy-specific value comes from the environment (or a local `.env` file created from
`.env.example`). Defaults are safe for local development with SQLite and no Redis.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

# --- Core -----------------------------------------------------------------------------------

SECRET_KEY: str = env("SECRET_KEY", default="<REDACTED>")
DEBUG: bool = env.bool("DEBUG", default=False)
ALLOWED_HOSTS: list[str] = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost", "testserver"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.registry",
    "apps.pricing",
    "apps.deliveries",
    "apps.audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # JSON compresses ~8x; a 20-row feed page is ~6.3 KB raw vs ~0.8 KB gzipped on 2G.
    "django.middleware.gzip.GZipMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # One append-only row per request to a protected endpoint (apps/audit/middleware.py).
    "apps.audit.middleware.AuditLogMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite by default; set DATABASE_URL=postgres://<REDACTED>@host:5432/kawa for Postgres.
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Kigali"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Django REST Framework ------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # Tokens for system integrations, sessions for staff in the browser; both set request.user.
    # Token comes first so an anonymous request gets 401 with a WWW-Authenticate challenge.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Tokens accept both `Token <key>` and `Bearer <key>`.
        "apps.accounts.authentication.TokenOrBearerAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        # Username and password on each request, for simple scripted clients (over HTTPS only).
        "rest_framework.authentication.BasicAuthentication",
    ],
    # Closed by default: a view is public only if it says so (status, price schedule, login), and
    # every other view must name the ROLE_POLICIES resource it serves (apps/accounts/permissions.py).
    # Anonymous callers are handled there too: ANONYMOUS_POLICY grants registrations, no reads.
    "DEFAULT_PERMISSION_CLASSES": ["apps.accounts.permissions.RolePolicyPermission"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.CreatedAtCursorPagination",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.kawa_exception_handler",
    "COERCE_DECIMAL_TO_STRING": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Kawa Network API",
    "DESCRIPTION": (
        "Farmer, plot and cherry-delivery registry for Kawa Network washing stations. "
        "Plot deforestation-risk checks run asynchronously; deliveries are never blocked by them."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "RiskStatusEnum": "apps.registry.models.RiskStatus",
        "GradeEnum": "apps.pricing.models.Grade",
        "AttemptOutcomeEnum": "apps.registry.models.AttemptOutcome",
    },
}

# --- Celery (async deforestation-risk checks) -----------------------------------------------

CELERY_BROKER_URL: str = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND: str = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_BROKER_TRANSPORT_OPTIONS: dict = env.json("CELERY_BROKER_TRANSPORT_OPTIONS", default={})
CELERY_TASK_ALWAYS_EAGER: bool = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TIMEZONE = TIME_ZONE
# Outcomes are persisted as RiskCheckAttempt rows, so Celery's result store is not needed. This also
# stops .delay() from subscribing to the result backend, which blocks for ~20 s when Redis is down.
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_HIJACK_ROOT_LOGGER = False  # keep the JSON LOGGING config below in the worker too
CELERY_RESULT_EXPIRES = timedelta(days=1)
# Fail fast when the broker is down so an API request never hangs on Redis; the periodic
# sweeper re-enqueues anything that could not be published.
CELERY_TASK_PUBLISH_RETRY_POLICY = {
    "max_retries": 2,
    "interval_start": 0,
    "interval_step": 0.2,
    "interval_max": 0.5,
}
CELERY_BROKER_CONNECTION_TIMEOUT = 2
CELERY_BEAT_SCHEDULE = {
    "requeue-stale-risk-checks": {
        "task": "apps.registry.tasks.requeue_stale_risk_checks",
        "schedule": timedelta(minutes=env.int("RISK_CHECK_SWEEP_MINUTES", default=15)),
    },
}

# --- Deforestation-risk registry ------------------------------------------------------------

# Empty REGISTRY_API_URL means the simulated registry is used (the only client in F1).
REGISTRY_API_URL: str = env("REGISTRY_API_URL", default="")
REGISTRY_API_TIMEOUT: float = env.float("REGISTRY_API_TIMEOUT", default=30.0)
RISK_REGISTRY_MIN_LATENCY: float = env.float("RISK_REGISTRY_MIN_LATENCY", default=2.0)
RISK_REGISTRY_MAX_LATENCY: float = env.float("RISK_REGISTRY_MAX_LATENCY", default=40.0)
RISK_REGISTRY_FAILURE_RATE: float = env.float("RISK_REGISTRY_FAILURE_RATE", default=0.2)
RISK_REGISTRY_FLAG_RATE: float = env.float("RISK_REGISTRY_FLAG_RATE", default=0.1)

RISK_CHECK_MAX_RETRIES: int = env.int("RISK_CHECK_MAX_RETRIES", default=8)
RISK_CHECK_BACKOFF_SECONDS: int = env.int("RISK_CHECK_BACKOFF_SECONDS", default=60)
RISK_CHECK_STALE_HOURS: int = env.int("RISK_CHECK_STALE_HOURS", default=6)
RISK_CHECK_MANUAL_REVIEW_DAYS: int = env.int("RISK_CHECK_MANUAL_REVIEW_DAYS", default=7)

# --- Domain limits --------------------------------------------------------------------------

PRICE_SCHEDULE_MAX_AGE_SECONDS: int = env.int("PRICE_SCHEDULE_MAX_AGE_SECONDS", default=60)

# --- Logging (one JSON object per line, so worker logs can be grepped by plot_id) -----------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "apps.core.logging.JsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
    },
}
```

### config/urls.py

```python
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.registry.urls")),
    path("api/", include("apps.pricing.urls")),
    path("api/", include("apps.deliveries.urls")),
    path("api/", include("apps.audit.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

handler404 = "apps.core.views.not_found"
handler500 = "apps.core.views.server_error"
```

### config/wsgi.py

```python
"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
```

### apps/accounts/admin.py

```python
from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "role", "washing_station"]
    list_filter = ["role", "washing_station"]
    search_fields = ["user__username"]
```

### apps/accounts/apps.py

```python
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
```

### apps/accounts/authentication.py

```python
from typing import Any

from rest_framework.authentication import TokenAuthentication, get_authorization_header
from rest_framework.request import Request


class TokenOrBearerAuthentication(TokenAuthentication):
    """DRF token authentication that also accepts the standard `Bearer` scheme (RFC 6750).

    `Authorization: Token <key>` and `Authorization: Bearer <key>` are the same token; clients
    written for OAuth/JWT-style APIs send `Bearer`. The 401 challenge still advertises `Token`.
    """

    def authenticate(self, request: Request) -> Any:
        auth = get_authorization_header(request).split()
        if len(auth) == 2 and auth[0].lower() == b"bearer":
            try:
                key = auth[1].decode()
            except UnicodeError:
                return None
            return self.authenticate_credentials(key)
        return super().authenticate(request)
```

### apps/accounts/field_rules.py

```python
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
            return getattr(instance.sector, f"reference_{self.axis}")
        return super().get_attribute(instance)


class CommercialTermField(serializers.DecimalField):
    """Price paid to the farmer; removed for roles without commercial terms (the auditor)."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)

    def hidden_for(self, policy: RolePolicy) -> bool:
        return not policy.commercial_terms


# Keeps every field whose `hidden_for(policy)` is true out of the response. A hidden field that can
# be written (the national ID on registration) stays accepted as input, write-only, so a role that
# may not see it can still record it; a hidden read-only field (prices) is removed. A comment, not
# a docstring, so serializers without their own docstring do not publish it in schema.yml.
class PolicyFieldsMixin:
    def get_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = super().get_fields()  # type: ignore[misc]
        context = self.context  # type: ignore[attr-defined]
        if is_schema_generation(context):
            return fields
        policy = policy_from_context(context)
        visible = {}
        for name, field in fields.items():
            if not (hasattr(field, "hidden_for") and field.hidden_for(policy)):
                visible[name] = field
            elif not field.read_only:
                # get_fields() returns fresh copies per serializer, so this does not leak.
                field.write_only = True
                visible[name] = field
        return visible
```

### apps/accounts/management/commands/seed_rbac_fixtures.py

```python
"""Create the F2 access-matrix fixtures (docs/autograding/F2_CONTRACT.md). Safe to run repeatedly.

Every value is copied from the contract. Records are written through the models, not the API:
plots skip register_plot so no risk-check job is queued. Re-running converges existing rows on
the seed values instead of duplicating them.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, UserProfile
from apps.deliveries.services import find_replay, record_delivery
from apps.pricing.services import get_active_price
from apps.registry.models import Farmer, Plot, Sector, WashingStation

PASSWORD = "GraderPass123!"

# username, role, washing station
USERS = [
    ("field_agent_user", Role.FIELD_AGENT, "Nyaruguru"),
    ("exporter_user", Role.EXPORTER_PARTNER, None),
    ("auditor_user", Role.COMPLIANCE_AUDITOR, None),
]

FARMER = {
    "full_name": "Uwimana Béatrice",
    "national_id": "1198770123456789",
    "member_number": "KWA-F-SEED-01",
    # Not in the contract; invented so it cannot collide with the F1 flow's +250780000000.
    "phone": "+250788999001",
}

# plot_code, sector, washing station, latitude, longitude
PLOTS = [
    ("KWA-SEED-K1", "Kigoma", "Nyaruguru", "-2.540000", "29.710000"),
    ("KWA-SEED-K2", "Kigoma", "Nyaruguru", "-2.660000", "29.790000"),
    ("KWA-SEED-M1", "Mbazi", "Kamonyi", "-2.510000", "29.520000"),
    ("KWA-SEED-M2", "Mbazi", "Kamonyi", "-2.900000", "29.900000"),
]
PLOT_AREA_HECTARES = Decimal("0.50")

# client_reference, plot_code; each delivery is recorded at its plot's washing station.
DELIVERIES = [
    ("seed-rbac-K1", "KWA-SEED-K1"),
    ("seed-rbac-M1", "KWA-SEED-M1"),
]
DELIVERY_WEIGHT_KG = Decimal("38.50")
DELIVERY_GRADE = "A"
DELIVERED_ON = date(2026, 3, 14)


class Command(BaseCommand):
    help = "Create the F2 role users, seed farmer, four fixture plots and two deliveries."

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        for username, role, station in USERS:
            self.seed_user(username, role, station)
        farmer = self.seed_farmer()
        plots = {code: self.seed_plot(farmer, code, *rest) for code, *rest in PLOTS}
        for client_reference, plot_code in DELIVERIES:
            self.seed_delivery(plots[plot_code], client_reference)
        self.stdout.write(
            self.style.SUCCESS(
                f"RBAC fixtures ready: {len(USERS)} users, farmer {farmer.member_number}, "
                f"{len(PLOTS)} plots, {len(DELIVERIES)} deliveries."
            )
        )

    def seed_user(self, username: str, role: str, station_name: str | None) -> None:
        user, _ = User.objects.get_or_create(username=username)
        # Reset on every run so a changed password or a deactivated account cannot break grading.
        user.set_password(PASSWORD)
        user.is_active = True
        user.save()
        station = WashingStation.objects.get(name=station_name) if station_name else None
        UserProfile.objects.update_or_create(user=user, defaults={"role": role, "washing_station": station})

    def seed_farmer(self) -> Farmer:
        # member_number is the farmer's natural key. The F1 contract flow registers the same
        # person and national ID under KWA-F-0417; that record is left alone, so the F1 flow
        # still creates and replays its own farmer after seeding.
        farmer = Farmer.objects.filter(member_number=FARMER["member_number"]).first() or Farmer()
        phone_owner = Farmer.objects.filter(phone=FARMER["phone"]).exclude(pk=farmer.pk).first()
        if phone_owner:
            raise CommandError(f"Seed phone {FARMER['phone']} already belongs to farmer {phone_owner.pk}.")
        for field, value in FARMER.items():
            setattr(farmer, field, value)
        farmer.save()
        return farmer

    def seed_plot(self, farmer: Farmer, code: str, sector: str, station: str, lat: str, lon: str) -> Plot:
        # update_or_create, not register_plot: no on_commit hook, so no risk-check job is queued.
        plot, _ = Plot.objects.update_or_create(
            plot_code=code,
            defaults={
                "farmer": farmer,
                "sector": Sector.objects.get(name=sector),
                "washing_station": WashingStation.objects.get(name=station),
                "latitude": Decimal(lat),
                "longitude": Decimal(lon),
                "area_hectares": PLOT_AREA_HECTARES,
            },
        )
        return plot

    def seed_delivery(self, plot: Plot, client_reference: str) -> None:
        # An existing delivery is kept as is: its price is a snapshot of what the farmer was paid.
        if find_replay(plot.washing_station.name, client_reference):
            return
        price = get_active_price(DELIVERY_GRADE)
        if price is None:
            raise CommandError(f"No active price for grade {DELIVERY_GRADE}; cannot record seed deliveries.")
        record_delivery(
            plot=plot,
            washing_station=plot.washing_station,
            weight_kg=DELIVERY_WEIGHT_KG,
            grade=DELIVERY_GRADE,
            price_entry=price,
            delivered_on=DELIVERED_ON,
            client_reference=client_reference,
        )
```

### apps/accounts/models.py

```python
from django.conf import settings
from django.db import models
from django.db.models import Q


class Role(models.TextChoices):
    """The F2 roles. What each one may do lives in apps/accounts/policies.py, not here."""

    FIELD_AGENT = "field_agent", "Field agent"
    EXPORTER_PARTNER = "exporter_partner", "Exporter partner"
    COMPLIANCE_AUDITOR = "compliance_auditor", "Compliance auditor"


class UserProfile(models.Model):
    """One role per staff user. A user without a profile has no API access at all."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=32, choices=Role.choices)
    # Field agents are scoped to one station; partners and auditors see every station.
    washing_station = models.ForeignKey(
        "registry.WashingStation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="staff_profiles",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(role__in=Role.values), name="profile_role_known"),
            # A field agent without a station would have no scope; anyone else with one would
            # suggest a scope that the policy does not apply.
            models.CheckConstraint(
                condition=(Q(role=Role.FIELD_AGENT) & Q(washing_station__isnull=False))
                | (~Q(role=Role.FIELD_AGENT) & Q(washing_station__isnull=True)),
                name="profile_station_iff_field_agent",
            ),
        ]

    def __str__(self) -> str:
        station = f" @ {self.washing_station}" if self.washing_station_id else ""
        return f"{self.user} ({self.role}{station})"
```

### apps/accounts/permissions.py

```python
from typing import TYPE_CHECKING

from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request

from .policies import Action, can

if TYPE_CHECKING:
    # DRF imports DEFAULT_PERMISSION_CLASSES while rest_framework.views is still loading.
    from rest_framework.views import APIView


class RolePolicyPermission(BasePermission):
    """Applies ROLE_POLICIES to a view. Deny by default: a view that does not name its
    `policy_resource` is refused for everyone, so a new endpoint cannot ship open by accident.

    Safe methods (GET, HEAD, OPTIONS) need READ on the resource; anything else needs WRITE. Which
    rows the user then sees is decided by visible_to() in the view's queryset, not here.
    """

    message = "Your role does not allow this."

    def has_permission(self, request: Request, view: "APIView") -> bool:
        resource = getattr(view, "policy_resource", None)
        if resource is None:
            return False
        action = Action.READ if request.method in SAFE_METHODS else Action.WRITE
        return can(request.user, resource, action)
```

### apps/accounts/policies.py

```python
"""Central role policies: the one place that says what each role may do.

Deny by default. Anything not granted here is refused: anonymous or inactive users, a role with
no policy, a field agent with no station, and any resource or action a policy does not list.
Views, querysets and serializers ask this module; they never test role names themselves.

A logged-in user who has no role profile at all gets NO_ROLE_POLICY: the F1 operations (register
farmers, plots and deliveries) under the most restrictive field rules. An anonymous caller gets
ANONYMOUS_POLICY: those registrations only, with no read access at all (see DECISION_LOG.md).

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


WRITE_ONLY = frozenset({Action.WRITE})

# Not logged in. Keeps the F1 registrations (POST farmers, plots, deliveries) working, as F1 had
# no login, but grants no reads: every list, detail and the audit log stay 401. Responses to a
# registration reveal the least (no national ID, sector points, no prices).
ANONYMOUS_POLICY = RolePolicy(
    grants={
        Resource.FARMERS: WRITE_ONLY,
        Resource.PLOTS: WRITE_ONLY,
        Resource.DELIVERIES: WRITE_ONLY,
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
    if user is None:
        return None
    if not user.is_authenticated:
        return ANONYMOUS_POLICY
    if not user.is_active:
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
```

### apps/accounts/scoping.py

```python
"""Record scoping: `Model.objects.visible_to(user)` returns only the rows that user's role may see.

Deny by default, like the policies it reads: a user with no policy gets an empty queryset. Every
view, sub-route and replay lookup starts from visible_to(), so a record outside the caller's scope
is a 404 (indistinguishable from one that does not exist), never a 403 that confirms it exists.
"""

from typing import Any, Self

from django.db import models
from django.db.models import Q

from .policies import AnyUser, RecordScope, policy_for, scoped_station_id


class StationScopedQuerySet(models.QuerySet):
    """Subclasses say how a row belongs to a station; the policy says whether that bounds the user."""

    def own_station_q(self, station_id: int) -> Q:
        raise NotImplementedError

    def visible_to(self, user: AnyUser) -> Self:
        policy = policy_for(user)
        if policy is None:
            return self.none()
        if policy.record_scope == RecordScope.ALL:
            return self
        station_id = scoped_station_id(user)
        return self.none() if station_id is None else self.filter(self.own_station_q(station_id))


# For serializers: every related field whose queryset supports visible_to() is narrowed to the
# requesting user, so a write can only point at records they may see. An out-of-scope id or name
# fails validation as "does not exist", the same as one that really does not exist.
# A comment, not a docstring: serializers without their own docstring would inherit it, and
# drf-spectacular would publish it as the component description in schema.yml.
class ScopedRelationsMixin:
    def get_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = super().get_fields()  # type: ignore[misc]
        request = self.context.get("request")  # type: ignore[attr-defined]
        if request is not None:
            for field in fields.values():
                target = getattr(field, "child_relation", field)
                queryset = getattr(target, "queryset", None)
                # ModelSerializer's auto-built relations hold the model's manager, not a queryset.
                if isinstance(queryset, models.Manager):
                    queryset = queryset.all()
                if isinstance(queryset, StationScopedQuerySet):
                    target.queryset = queryset.visible_to(request.user)
        return fields
```

### apps/accounts/urls.py

```python
from django.urls import path

from .views import ApiTokenView, StaffLoginView

urlpatterns = [
    path("auth/staff-login/", StaffLoginView.as_view(), name="staff-login"),
    path("auth/api-token/", ApiTokenView.as_view(), name="api-token"),
]
```

### apps/accounts/views.py

```python
"""Login endpoints. They only prove who the caller is (authentication). What that user may then
see is decided per request by apps/accounts/policies.py (authorization), so any valid user can
log in here, including one with no role profile."""

from django.contrib.auth import login
from django.contrib.auth.models import User
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

TokenResponse = inline_serializer("AuthToken", {"token": serializers.CharField()})
LOGIN_SCHEMA = extend_schema(
    request=AuthTokenSerializer,
    responses={200: TokenResponse, 400: OpenApiResponse(description="Wrong username or password.")},
)


class _CredentialsView(APIView):
    # No authentication on the login views themselves: a stale cookie or a bad Authorization
    # header must not stop someone from logging in again.
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def authenticated_user(self, request: Request) -> User:
        serializer = AuthTokenSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data["user"]


class StaffLoginView(_CredentialsView):
    """Staff in the browser: starts a Django session (cookie) and also returns the user's token."""

    @LOGIN_SCHEMA
    def post(self, request: Request) -> Response:
        user = self.authenticated_user(request)
        login(request._request, user)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})


class ApiTokenView(_CredentialsView):
    """System integrations: exchange credentials for a token sent as `Authorization: Token <key>`.
    No session is created."""

    @LOGIN_SCHEMA
    def post(self, request: Request) -> Response:
        user = self.authenticated_user(request)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})
```

### apps/audit/admin.py

```python
from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only: the trail can be inspected in the admin but not changed or pruned there."""

    list_display = ["occurred_at", "username", "role", "method", "path", "status_code", "coordinate_precision"]
    list_filter = ["role", "resource", "status_code"]
    search_fields = ["username", "path"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
```

### apps/audit/apps.py

```python
from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    label = "audit"
```

### apps/audit/filters.py

```python
import django_filters

from apps.accounts.policies import CoordinatePrecision, NationalIdVisibility

from .models import AuditLog


class AuditLogFilter(django_filters.FilterSet):
    username = django_filters.CharFilter()
    role = django_filters.CharFilter()
    resource = django_filters.CharFilter()
    status_code = django_filters.NumberFilter()
    # "Who saw exact coordinates?" is ?resource=plots&coordinate_precision=full
    coordinate_precision = django_filters.ChoiceFilter(choices=[(p.value, p.value) for p in CoordinatePrecision])
    # "Who saw farmer identity data?" is ?resource=farmers&national_id=last_four
    national_id = django_filters.ChoiceFilter(choices=[(v.value, v.value) for v in NationalIdVisibility])
    occurred_after = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    occurred_before = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="lt")

    class Meta:
        model = AuditLog
        fields = [
            "username",
            "role",
            "resource",
            "status_code",
            "coordinate_precision",
            "national_id",
            "occurred_after",
            "occurred_before",
        ]
```

### apps/audit/middleware.py

```python
"""Write one AuditLog row for every request to a view that names a ROLE_POLICIES resource.

Middleware rather than a view mixin, so no protected view can forget to log: whatever has a
`policy_resource` is audited, including requests refused with 401, 403 or 404. Public views
(status, price schedule, login) have no resource and are not logged.
"""

from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponse

from apps.accounts.policies import policy_for, profile_for

from .models import AuditLog


def policy_resource_of(request: HttpRequest) -> str | None:
    match = request.resolver_match
    view_class = getattr(match.func, "cls", None) if match else None
    resource = getattr(view_class, "policy_resource", None)
    return str(resource) if resource else None


def returned_ids(data: Any, kwargs: dict[str, Any]) -> list[int]:
    """Ids of the records in the response (a page, or one record); else the record in the URL."""
    rows = data.get("results", [data]) if isinstance(data, dict) else data if isinstance(data, list) else []
    ids = [row["id"] for row in rows if isinstance(row, dict) and isinstance(row.get("id"), int)]
    if not ids and str(kwargs.get("pk", "")).isdigit():
        ids = [int(kwargs["pk"])]
    return ids


class AuditLogMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        resource = policy_resource_of(request)
        if resource is not None:
            self.record(request, response, resource)
        return response

    def record(self, request: HttpRequest, response: HttpResponse, resource: str) -> None:
        # DRF copies the user it authenticated (session or token) onto the Django request.
        user = getattr(request, "user", None)
        authenticated = bool(user is not None and user.is_authenticated)
        profile = profile_for(user)
        policy = policy_for(user)
        match = request.resolver_match
        # Not wrapped in try/except: if the trail cannot be written, the request fails (500)
        # rather than serving data that leaves no record.
        AuditLog.objects.create(
            user=user if authenticated else None,
            username=user.get_username() if authenticated and user is not None else "",
            role=profile.role if profile else "",
            method=request.method or "",
            path=request.path[:255],
            endpoint=(match.view_name if match else "")[:100],
            status_code=response.status_code,
            resource=resource,
            object_ids=returned_ids(getattr(response, "data", None), match.kwargs if match else {}),
            coordinate_precision=policy.coordinates.value if policy else "",
            national_id=policy.national_id.value if policy else "",
            commercial_terms=policy.commercial_terms if policy else None,
        )
```

### apps/audit/models.py

```python
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone


class AppendOnlyError(Exception):
    """Raised on any attempt to change or remove an audit row."""


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs: Any) -> int:
        raise AppendOnlyError("Audit log rows cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise AppendOnlyError("Audit log rows cannot be deleted.")


class AuditLog(models.Model):
    """One row per request to a protected endpoint: who asked for what, and what they were shown.

    Append-only. Records identifiers and the field rules applied, never the data itself: no
    coordinates, national IDs, prices, request bodies or query strings.
    """

    occurred_at = models.DateTimeField(default=timezone.now, editable=False)
    # SET_NULL keeps the trail if an account is removed; `username` keeps who it was.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    username = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=32, blank=True)
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=255)
    endpoint = models.CharField(max_length=100, blank=True)
    status_code = models.PositiveSmallIntegerField()
    resource = models.CharField(max_length=32)
    object_ids = models.JSONField(default=list)
    # The field rules in force for this response (blank when the user had no policy).
    coordinate_precision = models.CharField(max_length=16, blank=True)
    national_id = models.CharField(max_length=16, blank=True)
    commercial_terms = models.BooleanField(null=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["-occurred_at", "-id"], name="audit_cursor_idx"),
            models.Index(fields=["username", "-occurred_at"], name="audit_user_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.occurred_at:%Y-%m-%d %H:%M:%S} {self.username or 'anonymous'} {self.method} {self.path}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise AppendOnlyError("Audit log rows cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise AppendOnlyError("Audit log rows cannot be deleted.")
```

### apps/audit/serializers.py

```python
from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """One request to a protected endpoint: who made it, what it returned, and which field rules
    applied. Holds record ids only, never coordinates, national IDs or prices."""

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "occurred_at",
            "username",
            "role",
            "method",
            "path",
            "endpoint",
            "status_code",
            "resource",
            "object_ids",
            "coordinate_precision",
            "national_id",
            "commercial_terms",
        ]
        read_only_fields = fields
        extra_kwargs = {
            "object_ids": {"help_text": "Ids of the records returned, or of the record named in the URL."},
            "national_id": {"help_text": "How national IDs were served: last_four or hidden."},
            "commercial_terms": {"help_text": "Whether prices were included; null if the user had no role."},
        }
```

### apps/audit/urls.py

```python
from django.urls import path

from .views import AuditLogListView

urlpatterns = [
    path("audit-log/", AuditLogListView.as_view(), name="audit-log"),
]
```

### apps/audit/views.py

```python
from rest_framework import generics

from apps.accounts.policies import Resource
from apps.core.pagination import CreatedAtCursorPagination

from .filters import AuditLogFilter
from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogPagination(CreatedAtCursorPagination):
    ordering = ("-occurred_at", "-id")


class AuditLogListView(generics.ListAPIView):
    """Who accessed farmer, plot and delivery data, newest first. Compliance auditors only.
    Reading this list is itself recorded."""

    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    pagination_class = AuditLogPagination
    filterset_class = AuditLogFilter
    policy_resource = Resource.AUDIT_LOG
```

### apps/core/apps.py

```python
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
```

### apps/core/exceptions.py

```python
"""One error envelope for every API failure.

Shape: {"error": {"code": str, "message": str, "details": dict}}
"""

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class Conflict(exceptions.APIException):
    """The request contradicts existing data: a write that raced past validation into a uniqueness
    constraint, or an idempotency key reused with a different body."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with existing data."
    default_code = "conflict"

    def __init__(self, detail: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.details = details or {}


def error_body(code: str, message: str, details: Any | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def kawa_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    # Duplicates that validation can see are 400s with field details. An IntegrityError only
    # reaches here when two requests raced past validation, so it is reported as a 409.
    if isinstance(exc, IntegrityError):
        logger.warning("api.integrity_conflict", extra={"error": str(exc)})
        exc = Conflict()
    elif isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(as_serializer_error(exc))
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound(str(exc) or None)
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied(str(exc) or None)

    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("api.unhandled_error", exc_info=exc)
        return Response(
            error_body("server_error", "An unexpected error occurred."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        details = response.data if isinstance(response.data, dict) else {"non_field_errors": response.data}
        response.data = error_body("validation_error", "The request data is invalid.", details)
    else:
        detail = response.data.get("detail", "") if isinstance(response.data, dict) else response.data
        code = getattr(exc, "default_code", "error")
        if isinstance(exc, exceptions.APIException):
            codes = exc.get_codes()
            code = codes if isinstance(codes, str) else code
        response.data = error_body(code, str(detail), getattr(exc, "details", None))
    return response
```

### apps/core/idempotency.py

```python
"""Idempotent POST for resources that have a natural key.

Station phones on 2G often resend a request whose response they never received. An identical
resend returns the existing record with 200 instead of a duplicate; the same key with different
details is a genuine conflict (409). Farmers replay on `member_number`, plots on `plot_code`, and
deliveries on `client_reference` (per station). All three share this one implementation.
"""

from typing import Any

from django.db.models import Model
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from .exceptions import Conflict


class NaturalKeyReplayMixin:
    """Mix into a viewset that has CreateModelMixin. Subclasses define the natural key."""

    natural_key_field: str

    def find_replay(self, data: dict[str, Any]) -> Model | None:
        raise NotImplementedError

    def replay_mismatches(self, existing: Model, data: dict[str, Any]) -> list[str]:
        raise NotImplementedError

    def replay_response(self, instance: Model, *, created: bool) -> Response:
        serializer = self.get_serializer(instance)  # type: ignore[attr-defined]
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            headers={"Idempotent-Replayed": "false" if created else "true"},
        )

    def create_new(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create path when no replay matched. Override when creation needs a service call."""
        response: Response = super().create(request, *args, **kwargs)  # type: ignore[misc]
        response["Idempotent-Replayed"] = "false"
        return response

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        existing = self.find_replay(data)
        if existing is None:
            return self.create_new(request, *args, **kwargs)
        mismatched = self.replay_mismatches(existing, data)
        if mismatched:
            key = str(data.get(self.natural_key_field, "")).strip()
            raise Conflict(
                f"{self.natural_key_field} {key!r} was already used for record {existing.pk} with different details.",
                details={"id": existing.pk, "mismatched_fields": mismatched},
            )
        return self.replay_response(existing, created=False)
```

### apps/core/logging.py

```python
"""JSON log formatter so `extra={...}` fields survive into worker and web logs."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

# Attributes every LogRecord has; anything else was passed through `extra=`.
_STANDARD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys() | {"message", "asctime"})


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
```

### apps/core/management/commands/seed_demo.py

```python
"""Load demo farmers, plots and deliveries for local exploration. Safe to run repeatedly.

Reference data (sectors, the Nyaruguru and Kamonyi stations, the active price schedule) comes
from data migrations, so it exists on every database after `migrate`.
"""

from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.deliveries.services import record_delivery
from apps.pricing.services import get_active_price
from apps.registry.models import Farmer, Plot, RiskStatus, Sector, WashingStation

FARMERS = [
    ("KWA-F-DEMO-01", "Mukamana Claudine", "+250788100001", "1198070000000101"),
    ("KWA-F-DEMO-02", "Habimana Jean Bosco", "+250788100002", "1197580000000202"),
    ("KWA-F-DEMO-03", "Nyirahabimana Esther", "+250728100003", None),
]

# plot_code, farmer member_number, sector, station, lat, lon, area, risk_status
PLOTS = [
    ("KWA-P-DEMO-01", "KWA-F-DEMO-01", "Kigoma", "Nyaruguru", "-2.541200", "29.712300", "0.35", RiskStatus.CLEAR),
    ("KWA-P-DEMO-02", "KWA-F-DEMO-02", "Kigoma", "Nyaruguru", "-2.655000", "29.781000", "0.60", RiskStatus.PENDING),
    ("KWA-P-DEMO-03", "KWA-F-DEMO-03", "Mbazi", "Kamonyi", "-2.512000", "29.521000", "0.25", RiskStatus.FLAGGED),
]


class Command(BaseCommand):
    help = "Create demo farmers, plots (with preset risk statuses) and deliveries."

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        farmers = {}
        for member_number, name, phone, national_id in FARMERS:
            farmers[member_number], _ = Farmer.objects.get_or_create(
                member_number=member_number,
                defaults={"full_name": name, "phone": phone, "national_id": national_id, "cooperative": "Huye"},
            )

        for code, member, sector, station, lat, lon, area, risk in PLOTS:
            # Created directly (not via register_plot) so demo data never needs a worker.
            plot, created = Plot.objects.get_or_create(
                plot_code=code,
                defaults={
                    "farmer": farmers[member],
                    "sector": Sector.objects.get(name=sector),
                    "washing_station": WashingStation.objects.get(name=station),
                    "latitude": Decimal(lat),
                    "longitude": Decimal(lon),
                    "area_hectares": Decimal(area),
                    "risk_status": risk,
                },
            )
            if not created:
                continue
            for i, (weight, grade) in enumerate([("38.50", "A"), ("22.00", "B")], start=1):
                price = get_active_price(grade)
                if price is None:
                    self.stderr.write(f"No active price for grade {grade}; skipping demo delivery.")
                    continue
                record_delivery(
                    plot=plot,
                    washing_station=plot.washing_station,
                    weight_kg=Decimal(weight),
                    grade=grade,
                    price_entry=price,
                    client_reference=f"demo-{code}-{i}",
                )

        self.stdout.write(
            self.style.SUCCESS(f"Demo data ready: {Farmer.objects.count()} farmers, {Plot.objects.count()} plots.")
        )
```

### apps/core/pagination.py

```python
"""Cursor pagination for every list endpoint.

Offset pagination breaks on the delivery feed: during harvest peak new rows arrive at the top
while a phone is paging, so offset pages shift (duplicates and skipped rows) and `OFFSET n` gets
slower as the table grows. A cursor encodes a position in a stable ordering instead.
"""

from rest_framework.pagination import CursorPagination


class CreatedAtCursorPagination(CursorPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    # `id` breaks ties between rows created in the same microsecond.
    ordering = ("-created_at", "-id")


class DeliveryFeedPagination(CreatedAtCursorPagination):
    # Backed by the composite index Delivery(washing_station, -recorded_at, -id).
    ordering = ("-recorded_at", "-id")
```

### apps/core/urls.py

```python
from django.urls import path

from .views import StatusView

urlpatterns = [
    path("status/", StatusView.as_view(), name="status"),
]
```

### apps/core/views.py

```python
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.registry.services import risk_check_backlog

from .exceptions import error_body


class StatusView(APIView):
    """Liveness probe, plus the risk-check backlog so a stalled worker is visible.

    `status` stays "ok" while the API can serve requests: a registry or worker problem must not
    make a load balancer pull a healthy API. `risk_checks.healthy` is false when plots are stale.
    Public, so a load balancer can probe it without credentials.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer(
            "Status",
            {
                "status": serializers.CharField(),
                "service": serializers.CharField(),
                "time": serializers.DateTimeField(),
                "risk_checks": inline_serializer(
                    "RiskCheckBacklog",
                    {
                        "pending": serializers.IntegerField(),
                        "unverified": serializers.IntegerField(),
                        "stale": serializers.IntegerField(),
                        "requires_manual_review": serializers.IntegerField(),
                        "last_attempt_at": serializers.DateTimeField(allow_null=True),
                        "healthy": serializers.BooleanField(),
                    },
                ),
            },
        )
    )
    def get(self, request: Request) -> Response:
        return Response(
            {"status": "ok", "service": "kawa-api", "time": timezone.now(), "risk_checks": risk_check_backlog()}
        )


def not_found(request: HttpRequest, exception: Exception) -> JsonResponse:
    return JsonResponse(error_body("not_found", "Not found."), status=404)


def server_error(request: HttpRequest) -> JsonResponse:
    return JsonResponse(error_body("server_error", "An unexpected error occurred."), status=500)
```

### apps/deliveries/admin.py

```python
from django.contrib import admin

from .models import Delivery


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "washing_station",
        "plot",
        "weight_kg",
        "grade",
        "amount_due_rwf",
        "plot_risk_status_at_delivery",
        "recorded_at",
    ]
    list_filter = ["washing_station", "grade", "plot_risk_status_at_delivery"]
    list_select_related = ["washing_station", "plot"]
    readonly_fields = ["unit_price_rwf", "amount_due_rwf", "plot_risk_status_at_delivery", "recorded_at"]
```

### apps/deliveries/apps.py

```python
from django.apps import AppConfig


class DeliveriesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.deliveries"
    label = "deliveries"
```

### apps/deliveries/filters.py

```python
import django_filters
from django.db.models import QuerySet

from apps.pricing.models import Grade
from apps.registry.models import RiskStatus

from .models import Delivery


class DeliveryFeedFilter(django_filters.FilterSet):
    washing_station = django_filters.CharFilter(field_name="washing_station__name", lookup_expr="iexact")
    grade = django_filters.ChoiceFilter(choices=Grade.choices)
    # Current plot status, i.e. what decides export eligibility today.
    risk_status = django_filters.ChoiceFilter(field_name="plot__risk_status", choices=RiskStatus.choices)
    # Phones pass the recorded_at of the newest row they hold to fetch only newer rows.
    since = django_filters.IsoDateTimeFilter(field_name="recorded_at", lookup_expr="gt")
    # ?exportable=false&risk_status=flagged is the review list for cherry already paid for.
    exportable = django_filters.BooleanFilter(method="filter_exportable")

    class Meta:
        model = Delivery
        fields = ["washing_station", "grade", "risk_status", "since", "exportable"]

    def filter_exportable(self, queryset: QuerySet[Delivery], name: str, value: bool) -> QuerySet[Delivery]:
        clear = {"plot__risk_status": RiskStatus.CLEAR}
        return queryset.filter(**clear) if value else queryset.exclude(**clear)
```

### apps/deliveries/models.py

```python
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.accounts.scoping import StationScopedQuerySet
from apps.pricing.models import Grade, PriceSchedule
from apps.registry.models import Plot, RiskStatus, WashingStation

# Upper bound for one farmer's delivery at the scale; larger values are data-entry errors.
MAX_DELIVERY_WEIGHT_KG = 500


class DeliveryQuerySet(StationScopedQuerySet):
    def own_station_q(self, station_id: int) -> Q:
        return Q(washing_station_id=station_id)


class Delivery(models.Model):
    """Cherry weighed in at a washing station.

    A delivery references the *plot* (not the farmer) so every export lot traces back to land.
    Price and plot risk status are snapshotted when the delivery is recorded, so a later price
    change or risk verdict never rewrites what the farmer was paid or what was known at the time.
    """

    plot = models.ForeignKey(Plot, on_delete=models.PROTECT, related_name="deliveries")
    washing_station = models.ForeignKey(WashingStation, on_delete=models.PROTECT, related_name="deliveries")
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2)
    grade = models.CharField(max_length=1, choices=Grade.choices)
    delivered_on = models.DateField(default=timezone.localdate)
    # Idempotency key generated on the phone; lets 2G retries replay safely.
    # NULL (not "") when absent, so the per-station unique constraint ignores it.
    client_reference = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001

    price_schedule = models.ForeignKey(PriceSchedule, on_delete=models.PROTECT, related_name="deliveries")
    unit_price_rwf = models.DecimalField(max_digits=10, decimal_places=2)
    amount_due_rwf = models.DecimalField(max_digits=12, decimal_places=2)
    plot_risk_status_at_delivery = models.CharField(max_length=12, choices=RiskStatus.choices)
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = DeliveryQuerySet.as_manager()

    class Meta:
        ordering = ["-recorded_at", "-id"]
        verbose_name_plural = "deliveries"
        indexes = [
            # The station feed: WHERE washing_station = ? ORDER BY recorded_at DESC, id DESC.
            models.Index(fields=["washing_station", "-recorded_at", "-id"], name="delivery_station_feed_idx"),
            models.Index(fields=["-recorded_at", "-id"], name="delivery_feed_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["washing_station", "client_reference"],
                condition=Q(client_reference__isnull=False),
                name="unique_client_reference_per_station",
            ),
            models.CheckConstraint(
                condition=Q(weight_kg__gt=0) & Q(weight_kg__lte=MAX_DELIVERY_WEIGHT_KG),
                name="delivery_weight_in_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.weight_kg} kg {self.grade} from {self.plot_id} at {self.washing_station_id}"

    @property
    def is_exportable(self) -> bool:
        """Only cherry from plots that are currently clear may enter a traceability export."""
        return self.plot.risk_status == RiskStatus.CLEAR
```

### apps/deliveries/serializers.py

```python
from datetime import date
from decimal import Decimal
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.accounts.field_rules import CommercialTermField, PolicyFieldsMixin
from apps.accounts.scoping import ScopedRelationsMixin
from apps.pricing.services import get_active_price
from apps.registry.models import Plot, WashingStation
from apps.registry.serializers import NameRelatedField

from .models import MAX_DELIVERY_WEIGHT_KG, Delivery

COMMERCIAL_HELP = "Commercial term: absent for compliance auditors."


class DeliverySerializer(PolicyFieldsMixin, ScopedRelationsMixin, serializers.ModelSerializer):
    """Full delivery record, used to record a delivery and to read one back."""

    plot = serializers.PrimaryKeyRelatedField(queryset=Plot.objects.select_related("washing_station"))
    washing_station = NameRelatedField(queryset=WashingStation.objects.all())
    weight_kg = serializers.DecimalField(max_digits=6, decimal_places=2)
    delivered_on = serializers.DateField(required=False)
    client_reference = serializers.CharField(max_length=64, required=False, allow_null=True, allow_blank=True)
    plot_code = serializers.CharField(source="plot.plot_code", read_only=True)
    farmer = serializers.IntegerField(source="plot.farmer_id", read_only=True)
    farmer_name = serializers.CharField(source="plot.farmer.full_name", read_only=True)
    season = serializers.CharField(source="price_schedule.season", read_only=True)
    is_exportable = serializers.BooleanField(read_only=True)
    unit_price_rwf = CommercialTermField(max_digits=10, decimal_places=2, help_text=COMMERCIAL_HELP)
    amount_due_rwf = CommercialTermField(max_digits=12, decimal_places=2, help_text=COMMERCIAL_HELP)

    class Meta:
        model = Delivery
        fields = [
            "id",
            "plot",
            "plot_code",
            "farmer",
            "farmer_name",
            "washing_station",
            "weight_kg",
            "grade",
            "delivered_on",
            "client_reference",
            "season",
            "unit_price_rwf",
            "amount_due_rwf",
            "plot_risk_status_at_delivery",
            "is_exportable",
            "recorded_at",
        ]
        read_only_fields = [
            "id",
            "unit_price_rwf",
            "amount_due_rwf",
            "plot_risk_status_at_delivery",
            "recorded_at",
        ]
        # Duplicate client_reference is an idempotent replay handled by the view, not a 400.
        validators: list[Any] = []

    def validate_weight_kg(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("Must be greater than 0.")
        if value > MAX_DELIVERY_WEIGHT_KG:
            raise serializers.ValidationError(f"Must be at most {MAX_DELIVERY_WEIGHT_KG} kg for one delivery.")
        return value

    def validate_delivered_on(self, value: date) -> date:
        if value > timezone.localdate():
            raise serializers.ValidationError("Delivery date cannot be in the future.")
        return value

    def validate_client_reference(self, value: str | None) -> str | None:
        return value.strip() or None if value else None

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        plot: Plot = attrs["plot"]
        station: WashingStation = attrs["washing_station"]
        if plot.washing_station_id != station.pk:
            raise serializers.ValidationError(
                {
                    "washing_station": [
                        f"Plot {plot.plot_code} delivers to {plot.washing_station.name}, not {station.name}."
                    ]
                }
            )
        price_entry = get_active_price(attrs["grade"])
        if price_entry is None:
            raise serializers.ValidationError(
                {"grade": [f"No active price for grade {attrs['grade']}; the station cannot pay for this delivery."]}
            )
        attrs["price_entry"] = price_entry
        return attrs


class DeliveryFeedSerializer(PolicyFieldsMixin, serializers.ModelSerializer):
    """Slim, flat row for the station feed: no nested objects, so pages stay small on 2G."""

    washing_station = serializers.CharField(source="washing_station.name", read_only=True)
    plot_code = serializers.CharField(source="plot.plot_code", read_only=True)
    farmer_name = serializers.CharField(source="plot.farmer.full_name", read_only=True)
    is_exportable = serializers.BooleanField(read_only=True)
    amount_due_rwf = CommercialTermField(max_digits=12, decimal_places=2, help_text=COMMERCIAL_HELP)

    class Meta:
        model = Delivery
        fields = [
            "id",
            "client_reference",
            "washing_station",
            "plot",
            "plot_code",
            "farmer_name",
            "weight_kg",
            "grade",
            "amount_due_rwf",
            "delivered_on",
            "recorded_at",
            "is_exportable",
        ]
        read_only_fields = fields
```

### apps/deliveries/services.py

```python
"""Recording cherry deliveries at the scale."""

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from apps.pricing.models import PriceEntry
from apps.registry.models import Plot, WashingStation

from .models import Delivery, DeliveryQuerySet

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")


def feed_queryset() -> DeliveryQuerySet:
    # One JOINed query per page: the feed serializer reads plot, farmer and station names.
    return Delivery.objects.select_related("plot__farmer", "washing_station").order_by("-recorded_at", "-id")


def find_replay(
    washing_station: Any, client_reference: Any, queryset: QuerySet[Delivery] | None = None
) -> Delivery | None:
    """Return the delivery a phone already recorded under this idempotency key, if any.

    API callers pass the deliveries they may see, so another station's key is never replayed back.
    """
    if not client_reference or not isinstance(client_reference, str) or not isinstance(washing_station, str):
        return None
    return (
        (feed_queryset() if queryset is None else queryset)
        .filter(washing_station__name__iexact=washing_station.strip(), client_reference=client_reference.strip())
        .first()
    )


def replay_mismatches(original: Delivery, data: dict[str, Any]) -> list[str]:
    """Fields where a replayed request disagrees with the delivery already recorded.

    A genuine 2G retry resends the identical body. A different body under the same key is a
    client bug (e.g. a reused reference) and must not be silently answered with someone else's
    delivery.
    """
    try:
        weight = Decimal(str(data.get("weight_kg")))
    except InvalidOperation:
        weight = None
    mismatched = []
    if str(data.get("plot")) != str(original.plot_id):
        mismatched.append("plot")
    if weight != original.weight_kg:
        mismatched.append("weight_kg")
    if data.get("grade") != original.grade:
        mismatched.append("grade")
    if data.get("delivered_on") not in (None, original.delivered_on.isoformat()):
        mismatched.append("delivered_on")
    return mismatched


def record_delivery(
    *,
    plot: Plot,
    washing_station: WashingStation,
    weight_kg: Decimal,
    grade: str,
    price_entry: PriceEntry,
    delivered_on: date | None = None,
    client_reference: str | None = None,
) -> tuple[Delivery, bool]:
    """Create a delivery, snapshotting today's price and the plot's current risk status.

    Deliveries are accepted whatever the plot's risk status: the farmer is paid the same day,
    and export eligibility is decided later from the plot's status (see ADR.md).
    Returns (delivery, created); created is False when the idempotency key was already used.
    """
    unit_price = price_entry.price_per_kg_rwf
    fields: dict[str, Any] = {
        "plot": plot,
        "washing_station": washing_station,
        "weight_kg": weight_kg,
        "grade": grade,
        "client_reference": client_reference,
        "price_schedule": price_entry.schedule,
        "unit_price_rwf": unit_price,
        "amount_due_rwf": (weight_kg * unit_price).quantize(CENT, rounding=ROUND_HALF_UP),
        "plot_risk_status_at_delivery": plot.risk_status,
    }
    if delivered_on is not None:
        fields["delivered_on"] = delivered_on
    try:
        with transaction.atomic():
            delivery = Delivery.objects.create(**fields)
    except IntegrityError:
        # Two retries of the same phone request raced past find_replay(); return the winner.
        existing = find_replay(washing_station.name, client_reference)
        if existing is None:
            raise
        return existing, False
    logger.info(
        "delivery.recorded",
        extra={
            "delivery_id": delivery.pk,
            "plot_id": plot.pk,
            "station": washing_station.code,
            "risk_status": plot.risk_status,
        },
    )
    return delivery, True
```

### apps/deliveries/urls.py

```python
from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import DeliveryViewSet, StationDeliveryFeedView

router = SimpleRouter(trailing_slash=True)
router.register("deliveries", DeliveryViewSet, basename="delivery")

urlpatterns = [
    path(
        "stations/<int:station_id>/deliveries/",
        StationDeliveryFeedView.as_view(),
        name="station-delivery-feed",
    ),
    *router.urls,
]
```

### apps/deliveries/views.py

```python
from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, mixins, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.accounts.policies import Resource
from apps.core.idempotency import NaturalKeyReplayMixin
from apps.core.pagination import DeliveryFeedPagination
from apps.registry.models import WashingStation

from . import services
from .filters import DeliveryFeedFilter
from .models import Delivery
from .serializers import DeliveryFeedSerializer, DeliverySerializer


class DeliveryViewSet(
    NaturalKeyReplayMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Record deliveries (idempotent on `client_reference`) and read the cursor-paginated feed."""

    pagination_class = DeliveryFeedPagination
    filterset_class = DeliveryFeedFilter
    natural_key_field = "client_reference"
    policy_resource = Resource.DELIVERIES

    def get_queryset(self) -> QuerySet[Delivery]:
        return services.feed_queryset().visible_to(self.request.user)

    def get_serializer_class(self) -> type[BaseSerializer]:
        return DeliveryFeedSerializer if self.action == "list" else DeliverySerializer

    def find_replay(self, data: dict[str, Any]) -> Delivery | None:
        return services.find_replay(data.get("washing_station"), data.get("client_reference"), self.get_queryset())

    def replay_mismatches(self, existing: Delivery, data: dict[str, Any]) -> list[str]:  # type: ignore[override]
        return services.replay_mismatches(existing, data)

    @extend_schema(
        responses={
            201: DeliverySerializer,
            200: OpenApiResponse(DeliverySerializer, description="Replay: this client_reference was already recorded."),
            409: OpenApiResponse(description="client_reference reused with a different body."),
        }
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().create(request, *args, **kwargs)

    def create_new(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # Pricing and the risk snapshot live in the service, so this does not use perform_create.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delivery, created = services.record_delivery(**serializer.validated_data)
        return self.replay_response(delivery, created=created)


class StationDeliveryFeedView(generics.ListAPIView):
    """Emmanuel's station feed: newest deliveries first, cursor-paginated."""

    serializer_class = DeliveryFeedSerializer
    pagination_class = DeliveryFeedPagination
    filterset_class = DeliveryFeedFilter
    policy_resource = Resource.DELIVERIES

    def get_queryset(self) -> QuerySet[Delivery]:
        if getattr(self, "swagger_fake_view", False):  # schema generation has no URL kwargs
            return Delivery.objects.none()
        user = self.request.user
        # Another station's feed is a 404 for a field agent, exactly like a station that does not exist.
        station = get_object_or_404(WashingStation.objects.visible_to(user), pk=self.kwargs["station_id"])
        return services.feed_queryset().visible_to(user).filter(washing_station=station)
```

### apps/pricing/admin.py

```python
from django.contrib import admin

from .models import PriceEntry, PriceSchedule


class PriceEntryInline(admin.TabularInline):
    model = PriceEntry
    extra = 0


@admin.register(PriceSchedule)
class PriceScheduleAdmin(admin.ModelAdmin):
    list_display = ["season", "effective_from", "is_active"]
    list_filter = ["is_active", "season"]
    inlines = [PriceEntryInline]
```

### apps/pricing/apps.py

```python
from django.apps import AppConfig


class PricingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pricing"
    label = "pricing"
```

### apps/pricing/models.py

```python
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Grade(models.TextChoices):
    """Cherry grade assigned at the scale."""

    A = "A", "Grade A (ripe red cherry)"
    B = "B", "Grade B (mixed ripeness)"
    C = "C", "Grade C (floaters / under-ripe)"


class PriceSchedule(models.Model):
    """Per-grade farm-gate prices for one season. Only one schedule per season may be active."""

    season = models.CharField(max_length=10, help_text='e.g. "2026A"')
    effective_from = models.DateField()
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-effective_from", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["season"], condition=Q(is_active=True), name="one_active_schedule_per_season"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.season} from {self.effective_from}{' (active)' if self.is_active else ''}"


class PriceEntry(models.Model):
    schedule = models.ForeignKey(PriceSchedule, on_delete=models.CASCADE, related_name="entries")
    grade = models.CharField(max_length=1, choices=Grade.choices)
    price_per_kg_rwf = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["grade"]
        constraints = [
            models.UniqueConstraint(fields=["schedule", "grade"], name="one_price_per_grade_per_schedule"),
            models.CheckConstraint(condition=Q(price_per_kg_rwf__gt=0), name="price_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.grade}: {self.price_per_kg_rwf} RWF/kg"
```

### apps/pricing/serializers.py

```python
from rest_framework import serializers

from .models import PriceEntry, PriceSchedule


class PriceEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceEntry
        fields = ["grade", "price_per_kg_rwf"]


class PriceScheduleSerializer(serializers.ModelSerializer):
    currency = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()
    prices = PriceEntrySerializer(source="entries", many=True)

    class Meta:
        model = PriceSchedule
        fields = ["id", "season", "effective_from", "currency", "unit", "prices"]

    def get_currency(self, obj: PriceSchedule) -> str:
        return "RWF"

    def get_unit(self, obj: PriceSchedule) -> str:
        return "kg"
```

### apps/pricing/services.py

```python
from datetime import date

from django.db import transaction
from django.utils import timezone

from .models import PriceEntry, PriceSchedule


def get_active_schedule(on: date | None = None) -> PriceSchedule | None:
    """The schedule stations pay from today: active, already in effect, most recent first."""
    on = on or timezone.localdate()
    return (
        PriceSchedule.objects.filter(is_active=True, effective_from__lte=on)
        .prefetch_related("entries")
        .order_by("-effective_from", "-id")
        .first()
    )


def get_active_price(grade: str, on: date | None = None) -> PriceEntry | None:
    return (
        PriceEntry.objects.select_related("schedule")
        .filter(schedule__is_active=True, schedule__effective_from__lte=on or timezone.localdate(), grade=grade)
        .order_by("-schedule__effective_from", "-schedule_id")
        .first()
    )


@transaction.atomic
def activate_schedule(schedule: PriceSchedule) -> PriceSchedule:
    """Make `schedule` the season's only active schedule (enforced by a DB constraint too)."""
    PriceSchedule.objects.filter(season=schedule.season, is_active=True).exclude(pk=schedule.pk).update(is_active=False)
    schedule.is_active = True
    schedule.save(update_fields=["is_active"])
    return schedule
```

### apps/pricing/urls.py

```python
from django.urls import path

from .views import PriceScheduleView

urlpatterns = [
    path("price-schedule/", PriceScheduleView.as_view(), name="price-schedule"),
]
```

### apps/pricing/views.py

```python
from django.conf import settings
from django.utils.cache import patch_cache_control
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import PriceScheduleSerializer
from .services import get_active_schedule


class PriceScheduleView(APIView):
    """Active season's per-grade farm-gate prices.

    Not cached on the server: every request reads the database, so a price change is visible to
    the next request. Clients may reuse a response for PRICE_SCHEDULE_MAX_AGE_SECONDS (default
    60 s), which is the whole staleness window. Public: it is the published price list.
    """

    permission_classes = [AllowAny]

    @extend_schema(responses=PriceScheduleSerializer)
    def get(self, request: Request) -> Response:
        schedule = get_active_schedule()
        if schedule is None:
            raise NotFound("No active price schedule.")
        response = Response(PriceScheduleSerializer(schedule).data)
        patch_cache_control(response, public=True, max_age=settings.PRICE_SCHEDULE_MAX_AGE_SECONDS)
        return response
```

### apps/registry/admin.py

```python
from django.contrib import admin

from .models import Farmer, Plot, RiskCheckAttempt, Sector, WashingStation


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ["name", "district", "reference_latitude", "reference_longitude"]


@admin.register(WashingStation)
class WashingStationAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "sector"]


@admin.register(Farmer)
class FarmerAdmin(admin.ModelAdmin):
    list_display = ["full_name", "member_number", "phone", "cooperative", "created_at"]
    search_fields = ["full_name", "member_number", "phone"]


class RiskCheckAttemptInline(admin.TabularInline):
    model = RiskCheckAttempt
    extra = 0
    readonly_fields = ["attempt_number", "outcome", "started_at", "finished_at", "duration_ms", "error_message"]


@admin.register(Plot)
class PlotAdmin(admin.ModelAdmin):
    list_display = ["plot_code", "farmer", "sector", "washing_station", "risk_status", "risk_checked_at"]
    list_filter = ["risk_status", "washing_station", "sector"]
    search_fields = ["plot_code", "farmer__full_name"]
    inlines = [RiskCheckAttemptInline]
```

### apps/registry/apps.py

```python
from django.apps import AppConfig


class RegistryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.registry"
    label = "registry"
```

### apps/registry/clients.py

```python
"""Clients for the external deforestation-risk registry.

The real registry is slow (seconds to tens of seconds) and has outages lasting hours, so it is
only ever called from the Celery worker, never from a request/response cycle.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from django.conf import settings


class RegistryError(Exception):
    """Base class for transient registry failures that are worth retrying."""

    outcome: str = "error"


class RegistryUnavailable(RegistryError):
    """Registry answered with an error or refused the connection."""

    outcome = "error"


class RegistryTimeout(RegistryError):
    """Registry did not answer within REGISTRY_API_TIMEOUT seconds."""

    outcome = "timeout"


@dataclass(frozen=True)
class RiskAssessment:
    status: Literal["clear", "flagged"]
    reference: str


class RiskRegistryClient(Protocol):
    def check_plot(self, *, plot_code: str, latitude: Decimal, longitude: Decimal) -> RiskAssessment: ...


class SimulatedRiskRegistry:
    """Stand-in for the registry with realistic latency, outages and timeouts."""

    def __init__(
        self,
        *,
        min_latency: float,
        max_latency: float,
        failure_rate: float,
        flag_rate: float,
        timeout: float,
        rng: random.Random | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_latency = min_latency
        self.max_latency = max(max_latency, min_latency)
        self.failure_rate = failure_rate
        self.flag_rate = flag_rate
        self.timeout = timeout
        self._rng = rng or random.Random()
        self._sleep = sleep

    def check_plot(self, *, plot_code: str, latitude: Decimal, longitude: Decimal) -> RiskAssessment:
        latency = self._rng.uniform(self.min_latency, self.max_latency)
        if latency > self.timeout:
            self._sleep(self.timeout)
            raise RegistryTimeout(f"registry did not answer within {self.timeout:.0f}s")
        self._sleep(latency)
        if self._rng.random() < self.failure_rate:
            raise RegistryUnavailable("registry returned 503 Service Unavailable")
        status: Literal["clear", "flagged"] = "flagged" if self._rng.random() < self.flag_rate else "clear"
        return RiskAssessment(status=status, reference=f"SIM-{plot_code}")


def get_registry_client() -> RiskRegistryClient:
    """Return the configured registry client.

    F1 ships only the simulator; a real HTTP client for REGISTRY_API_URL plugs in here.
    """
    return SimulatedRiskRegistry(
        min_latency=settings.RISK_REGISTRY_MIN_LATENCY,
        max_latency=settings.RISK_REGISTRY_MAX_LATENCY,
        failure_rate=settings.RISK_REGISTRY_FAILURE_RATE,
        flag_rate=settings.RISK_REGISTRY_FLAG_RATE,
        timeout=settings.REGISTRY_API_TIMEOUT,
    )
```

### apps/registry/filters.py

```python
from datetime import timedelta

import django_filters
from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils import timezone

from .models import Plot, RiskStatus


def manual_review_q() -> Q:
    """Plots whose check has stayed unverified past the policy window (ADR-001)."""
    cutoff = timezone.now() - timedelta(days=settings.RISK_CHECK_MANUAL_REVIEW_DAYS)
    return Q(risk_status=RiskStatus.UNVERIFIED, created_at__lte=cutoff)


class PlotFilter(django_filters.FilterSet):
    farmer = django_filters.NumberFilter(field_name="farmer_id")
    sector = django_filters.CharFilter(field_name="sector__name", lookup_expr="iexact")
    washing_station = django_filters.CharFilter(field_name="washing_station__name", lookup_expr="iexact")
    risk_status = django_filters.ChoiceFilter(choices=RiskStatus.choices)
    # The compliance review queue: ?requires_manual_review=true
    requires_manual_review = django_filters.BooleanFilter(method="filter_requires_manual_review")

    class Meta:
        model = Plot
        fields = ["farmer", "sector", "washing_station", "risk_status", "requires_manual_review"]

    def filter_requires_manual_review(self, queryset: QuerySet[Plot], name: str, value: bool) -> QuerySet[Plot]:
        return queryset.filter(manual_review_q()) if value else queryset.exclude(manual_review_q())
```

### apps/registry/models.py

```python
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.accounts.scoping import StationScopedQuerySet

# Rwanda's bounding box, padded. Coordinates outside it are typos, not plots. It is a coarse check:
# the southern edge sits below the real border (~-2.84) so the F2 fixture plot M2 (-2.90) fits.
# Polygon-based border validation is deferred (see DECISION_LOG.md).
RWANDA_LAT_MIN, RWANDA_LAT_MAX = Decimal("-2.95"), Decimal("-1.04")
RWANDA_LON_MIN, RWANDA_LON_MAX = Decimal("28.85"), Decimal("30.90")
MAX_PLOT_AREA_HECTARES = Decimal("50")


class Sector(models.Model):
    """Administrative sector. Exporter partners receive a plot's sector reference point instead of
    the plot's own coordinates, so location precision is keyed to the sector."""

    name = models.CharField(max_length=80, unique=True)
    district = models.CharField(max_length=80)
    # The sector's reference point: what exporters receive instead of a plot's own coordinates, so
    # every plot in the sector reports the same point. Deliberately not inside the sector: no
    # rounding of a plot coordinate reaches it (migration 0010, DECISION_LOG.md).
    reference_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    reference_longitude = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(reference_latitude__gte=RWANDA_LAT_MIN, reference_latitude__lte=RWANDA_LAT_MAX)
                & Q(reference_longitude__gte=RWANDA_LON_MIN, reference_longitude__lte=RWANDA_LON_MAX),
                name="sector_reference_point_inside_rwanda",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.district})"

    @property
    def reference_point(self) -> tuple[Decimal, Decimal]:
        return self.reference_latitude, self.reference_longitude


class WashingStationQuerySet(StationScopedQuerySet):
    def own_station_q(self, station_id: int) -> Q:
        return Q(pk=station_id)


class WashingStation(models.Model):
    name = models.CharField(max_length=80, unique=True)
    code = models.CharField(max_length=16, unique=True)
    sector = models.ForeignKey(Sector, on_delete=models.PROTECT, related_name="washing_stations")

    objects = WashingStationQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class FarmerQuerySet(StationScopedQuerySet):
    def own_station_q(self, station_id: int) -> Q:
        # A station's farmers: anyone with a plot delivering there, plus farmers registered there
        # who have no plot yet. Exists() rather than a join, so a farmer with two plots is one row.
        has_plot_here = Exists(Plot.objects.filter(farmer=OuterRef("pk"), washing_station_id=station_id))
        return has_plot_here | Q(home_station_id=station_id)


class Farmer(models.Model):
    full_name = models.CharField(max_length=150)
    member_number = models.CharField(max_length=32, unique=True)
    cooperative = models.CharField(max_length=120, blank=True)
    # Stored in E.164 (+2507XXXXXXXX); the serializer normalises local 07XXXXXXXX input.
    phone = models.CharField(max_length=13, unique=True)
    # Not unique: one person can hold two cooperative memberships (two member numbers), and the
    # F2 seed farmer shares the F1 contract farmer's ID. member_number is the farmer's natural key.
    # NULL (not "") when absent, as before; replays compare against None.
    national_id = models.CharField(max_length=16, null=True, blank=True, db_index=True)  # noqa: DJ001
    home_station = models.ForeignKey(
        WashingStation, on_delete=models.PROTECT, null=True, blank=True, related_name="farmers"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = FarmerQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            # Matches the cursor ordering of GET /api/farmers/, so each page is an index range scan.
            models.Index(fields=["-created_at", "-id"], name="farmer_list_cursor_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.member_number})"


class RiskStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CLEAR = "clear", "Clear"
    FLAGGED = "flagged", "Flagged"
    # Registry never answered after all retries. Not a verdict; the sweeper keeps retrying.
    UNVERIFIED = "unverified", "Unverified"


class PlotQuerySet(StationScopedQuerySet):
    def own_station_q(self, station_id: int) -> Q:
        return Q(washing_station_id=station_id)


class Plot(models.Model):
    farmer = models.ForeignKey(Farmer, on_delete=models.PROTECT, related_name="plots")
    plot_code = models.CharField(max_length=32, unique=True)
    label = models.CharField(max_length=100, blank=True)
    # Foreign keys are indexed automatically, which covers Plot(sector) and Plot(washing_station).
    sector = models.ForeignKey(Sector, on_delete=models.PROTECT, related_name="plots")
    washing_station = models.ForeignKey(WashingStation, on_delete=models.PROTECT, related_name="plots")
    area_hectares = models.DecimalField(max_digits=8, decimal_places=4)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    risk_status = models.CharField(max_length=12, choices=RiskStatus.choices, default=RiskStatus.PENDING)
    risk_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = PlotQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            # Serves the risk_status filter and the stale-check sweeper (status + age).
            models.Index(fields=["risk_status", "created_at"], name="plot_risk_status_created_idx"),
            # Matches the cursor ordering of GET /api/plots/, so each page is an index range scan.
            models.Index(fields=["-created_at", "-id"], name="plot_list_cursor_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(area_hectares__gt=0) & Q(area_hectares__lte=MAX_PLOT_AREA_HECTARES),
                name="plot_area_in_range",
            ),
            models.CheckConstraint(
                condition=Q(latitude__gte=RWANDA_LAT_MIN, latitude__lte=RWANDA_LAT_MAX)
                & Q(longitude__gte=RWANDA_LON_MIN, longitude__lte=RWANDA_LON_MAX),
                name="plot_inside_rwanda",
            ),
        ]

    def __str__(self) -> str:
        return self.plot_code

    @property
    def requires_manual_review(self) -> bool:
        """Unverified for longer than the policy window: a person must look at it."""
        if self.risk_status != RiskStatus.UNVERIFIED:
            return False
        window = timedelta(days=settings.RISK_CHECK_MANUAL_REVIEW_DAYS)
        return timezone.now() - self.created_at >= window


class AttemptOutcome(models.TextChoices):
    RUNNING = "running", "Running"
    CLEAR = "clear", "Clear"
    FLAGGED = "flagged", "Flagged"
    ERROR = "error", "Error"
    TIMEOUT = "timeout", "Timeout"


class RiskCheckAttempt(models.Model):
    """One call to the deforestation-risk registry. This table is the audit trail of retries."""

    plot = models.ForeignKey(Plot, on_delete=models.CASCADE, related_name="risk_checks")
    attempt_number = models.PositiveIntegerField()
    task_id = models.CharField(max_length=255, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=10, choices=AttemptOutcome.choices, default=AttemptOutcome.RUNNING)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["plot", "attempt_number"]
        indexes = [models.Index(fields=["plot", "started_at"], name="riskcheck_plot_started_idx")]
        constraints = [
            models.UniqueConstraint(fields=["plot", "attempt_number"], name="unique_attempt_number_per_plot"),
        ]

    def __str__(self) -> str:
        return f"{self.plot_id} #{self.attempt_number}: {self.outcome}"
```

### apps/registry/serializers.py

```python
import re
from decimal import Decimal
from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.accounts.field_rules import (
    CoordinateField,
    NationalIdField,
    PolicyFieldsMixin,
    policy_from_context,
)
from apps.accounts.policies import CoordinatePrecision, scoped_station_id
from apps.accounts.scoping import ScopedRelationsMixin

from .models import (
    MAX_PLOT_AREA_HECTARES,
    RWANDA_LAT_MAX,
    RWANDA_LAT_MIN,
    RWANDA_LON_MAX,
    RWANDA_LON_MIN,
    Farmer,
    Plot,
    RiskCheckAttempt,
    Sector,
    WashingStation,
)
from .services import register_farmer, register_plot
from .validators import normalise_rwandan_phone

_NATIONAL_ID = re.compile(r"^\d{16}$")
COORDINATE_HELP = (
    "Stored value for field agents and auditors. For exporter partners, the sector's reference point "
    "(identical for every plot in the sector); see coordinate_precision."
)


class RwandanPhoneField(serializers.CharField):
    """Accepts +2507XXXXXXXX, 2507XXXXXXXX or 07XXXXXXXX and stores E.164 (+2507XXXXXXXX).

    Normalising here (not in validate_phone) means the uniqueness check compares normalised
    numbers, so "0780000000" and "+250780000000" are recognised as the same farmer.
    """

    def to_internal_value(self, data: Any) -> str:
        phone = normalise_rwandan_phone(super().to_internal_value(data))
        if phone is None:
            raise serializers.ValidationError("Enter a Rwandan mobile number such as +250780000000 or 0780000000.")
        return phone


class NameRelatedField(serializers.SlugRelatedField):
    """Refers to a sector or washing station by its name, e.g. "Nyaruguru"."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(slug_field="name", **kwargs)

    def to_internal_value(self, data: Any) -> Any:
        try:
            return self.get_queryset().get(name__iexact=str(data).strip())
        except (self.get_queryset().model.DoesNotExist, TypeError, ValueError):
            self.fail("does_not_exist", slug_name=self.slug_field, value=str(data))


class SectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sector
        fields = ["id", "name", "district"]


class WashingStationSerializer(serializers.ModelSerializer):
    sector = serializers.CharField(source="sector.name", read_only=True)

    class Meta:
        model = WashingStation
        fields = ["id", "name", "code", "sector"]


class FarmerSerializer(PolicyFieldsMixin, ScopedRelationsMixin, serializers.ModelSerializer):
    phone = RwandanPhoneField(
        max_length=20,
        validators=[UniqueValidator(Farmer.objects.all(), message="A farmer with this phone number already exists.")],
    )
    national_id = NationalIdField(
        max_length=16,
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="16 digits. Read back as its last 4 digits for field agents; absent for other roles.",
    )
    home_station = NameRelatedField(queryset=WashingStation.objects.all(), required=False, allow_null=True)

    class Meta:
        model = Farmer
        fields = [
            "id",
            "full_name",
            "member_number",
            "cooperative",
            "phone",
            "national_id",
            "home_station",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_full_name(self, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise serializers.ValidationError("Enter the farmer's full name.")
        return value

    def validate_national_id(self, value: str | None) -> str | None:
        if not value:
            return None
        if not _NATIONAL_ID.match(value):
            raise serializers.ValidationError("National ID must be exactly 16 digits.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # A field agent's new farmer belongs to their station, so it stays visible to them (and to
        # an idempotent resend) before it has a plot. Another station is rejected by the scoped field.
        request = self.context.get("request")
        station_id = scoped_station_id(request.user) if request else None
        if station_id is not None and attrs.get("home_station") is None:
            attrs["home_station"] = WashingStation.objects.get(pk=station_id)
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Farmer:
        return register_farmer(validated_data)


class PlotSerializer(PolicyFieldsMixin, ScopedRelationsMixin, serializers.ModelSerializer):
    sector = NameRelatedField(queryset=Sector.objects.all())
    washing_station = NameRelatedField(queryset=WashingStation.objects.all())
    latitude = CoordinateField(axis="latitude", help_text=COORDINATE_HELP)
    longitude = CoordinateField(axis="longitude", help_text=COORDINATE_HELP)
    coordinate_precision = serializers.SerializerMethodField(
        help_text='"full": the plot\'s stored coordinates. "sector": the sector\'s reference point.'
    )
    area_hectares = serializers.DecimalField(
        max_digits=8,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        max_value=MAX_PLOT_AREA_HECTARES,
    )
    requires_manual_review = serializers.BooleanField(read_only=True)

    class Meta:
        model = Plot
        fields = [
            "id",
            "farmer",
            "plot_code",
            "label",
            "sector",
            "washing_station",
            "latitude",
            "longitude",
            "area_hectares",
            "risk_status",
            "risk_checked_at",
            "requires_manual_review",
            "coordinate_precision",
            "created_at",
        ]
        read_only_fields = ["id", "risk_status", "risk_checked_at", "created_at"]

    def validate_latitude(self, value: Decimal) -> Decimal:
        if not RWANDA_LAT_MIN <= value <= RWANDA_LAT_MAX:
            raise serializers.ValidationError(f"Latitude must be inside Rwanda ({RWANDA_LAT_MIN} to {RWANDA_LAT_MAX}).")
        return value

    def validate_longitude(self, value: Decimal) -> Decimal:
        if not RWANDA_LON_MIN <= value <= RWANDA_LON_MAX:
            raise serializers.ValidationError(
                f"Longitude must be inside Rwanda ({RWANDA_LON_MIN} to {RWANDA_LON_MAX})."
            )
        return value

    @extend_schema_field(serializers.ChoiceField(choices=[p.value for p in CoordinatePrecision]))
    def get_coordinate_precision(self, plot: Plot) -> str:
        return policy_from_context(self.context).coordinates.value

    def create(self, validated_data: dict[str, Any]) -> Plot:
        return register_plot(validated_data)


class RiskCheckAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskCheckAttempt
        fields = [
            "attempt_number",
            "outcome",
            "started_at",
            "finished_at",
            "duration_ms",
            "error_message",
            "task_id",
        ]
        read_only_fields = fields
```

### apps/registry/services.py

```python
"""Business operations for farmers, plots and risk checks. Views and tasks call these."""

import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Exists, Max, OuterRef, QuerySet
from django.utils import timezone

from .clients import RiskAssessment
from .models import AttemptOutcome, Farmer, Plot, RiskCheckAttempt, RiskStatus
from .validators import normalise_rwandan_phone

logger = logging.getLogger(__name__)

SETTLED_STATUSES = frozenset({RiskStatus.CLEAR, RiskStatus.FLAGGED})
# Hard ceiling for one registry call inside the worker (client timeout + margin).
ATTEMPT_SOFT_TIME_LIMIT_SECONDS = int(settings.REGISTRY_API_TIMEOUT) + 30


def register_farmer(data: dict[str, Any]) -> Farmer:
    return Farmer.objects.create(**data)


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def find_farmer_replay(data: dict[str, Any], queryset: QuerySet[Farmer]) -> Farmer | None:
    """`queryset` is what the caller may see: a key held by a farmer outside it is not a replay
    (it falls through to validation, which reports the duplicate without returning the record)."""
    member_number = data.get("member_number")
    if not isinstance(member_number, str) or not member_number.strip():
        return None
    return queryset.select_related("home_station").filter(member_number=member_number.strip()).first()


def farmer_replay_mismatches(farmer: Farmer, data: dict[str, Any]) -> list[str]:
    """Fields where a resent registration disagrees with the stored farmer (after normalising)."""
    mismatched = []
    if _text(data.get("full_name")) != farmer.full_name:
        mismatched.append("full_name")
    if normalise_rwandan_phone(_text(data.get("phone"))) != farmer.phone:
        mismatched.append("phone")
    if (_text(data.get("national_id")) or None) != farmer.national_id:
        mismatched.append("national_id")
    if _text(data.get("cooperative")) != farmer.cooperative:
        mismatched.append("cooperative")
    return mismatched


def find_plot_replay(data: dict[str, Any], queryset: QuerySet[Plot]) -> Plot | None:
    """`queryset` is what the caller may see; see find_farmer_replay."""
    plot_code = data.get("plot_code")
    if not isinstance(plot_code, str) or not plot_code.strip():
        return None
    return queryset.select_related("sector", "washing_station").filter(plot_code=plot_code.strip()).first()


def plot_replay_mismatches(plot: Plot, data: dict[str, Any]) -> list[str]:
    """Fields where a resent plot registration disagrees with the stored plot."""
    mismatched = []
    if _text(data.get("farmer")) != str(plot.farmer_id):
        mismatched.append("farmer")
    if _text(data.get("sector")).lower() != plot.sector.name.lower():
        mismatched.append("sector")
    if _text(data.get("washing_station")).lower() != plot.washing_station.name.lower():
        mismatched.append("washing_station")
    for field in ("latitude", "longitude", "area_hectares"):
        if _decimal(data.get(field)) != getattr(plot, field):
            mismatched.append(field)
    return mismatched


def register_plot(data: dict[str, Any]) -> Plot:
    """Create a plot as `pending` and queue its risk check once the row is committed.

    The registry is never called here: registration must answer in well under a second on 2G,
    while the registry can take 40 seconds or be down for hours.
    """
    with transaction.atomic():
        plot = Plot.objects.create(risk_status=RiskStatus.PENDING, **data)
        transaction.on_commit(lambda: enqueue_risk_check(plot.pk))
    return plot


def enqueue_risk_check(plot_id: int) -> bool:
    """Publish the risk-check task. A broker outage must not fail the farmer's registration:
    the plot stays `pending` and `requeue_stale_risk_checks` picks it up later."""
    from .tasks import run_risk_check

    try:
        run_risk_check.delay(plot_id)
    except Exception:  # any broker/transport failure is handled the same way
        logger.exception("risk_check.enqueue_failed", extra={"plot_id": plot_id})
        return False
    logger.info("risk_check.enqueued", extra={"plot_id": plot_id})
    return True


@transaction.atomic
def start_attempt(plot: Plot, task_id: str) -> RiskCheckAttempt:
    """Open the next numbered attempt. The plot row lock serialises concurrent tasks for the same
    plot (e.g. a late retry overlapping a sweeper requeue); the unique constraint backs it up."""
    Plot.objects.select_for_update().filter(pk=plot.pk).exists()
    last = RiskCheckAttempt.objects.filter(plot=plot).aggregate(n=Max("attempt_number"))["n"] or 0
    return RiskCheckAttempt.objects.create(plot=plot, attempt_number=last + 1, task_id=task_id)


def finish_attempt(attempt: RiskCheckAttempt, outcome: str, error_message: str = "") -> RiskCheckAttempt:
    attempt.finished_at = timezone.now()
    attempt.duration_ms = int((attempt.finished_at - attempt.started_at).total_seconds() * 1000)
    attempt.outcome = outcome
    attempt.error_message = error_message
    attempt.save(update_fields=["finished_at", "duration_ms", "outcome", "error_message"])
    return attempt


def apply_assessment(plot: Plot, assessment: RiskAssessment) -> Plot:
    plot.risk_status = RiskStatus(assessment.status)
    plot.risk_checked_at = timezone.now()
    plot.save(update_fields=["risk_status", "risk_checked_at"])
    return plot


def mark_unverified(plot: Plot) -> Plot:
    """Retries are exhausted. `unverified` means "no answer yet", not a verdict."""
    if plot.risk_status not in SETTLED_STATUSES:
        plot.risk_status = RiskStatus.UNVERIFIED
        plot.save(update_fields=["risk_status"])
    return plot


def stale_plot_ids(limit: int = 500) -> list[int]:
    """Plots still waiting on the registry with no attempt inside the stale window."""
    cutoff = timezone.now() - timedelta(hours=settings.RISK_CHECK_STALE_HOURS)
    recent_attempt = RiskCheckAttempt.objects.filter(plot=OuterRef("pk"), started_at__gte=cutoff)
    return list(
        Plot.objects.filter(risk_status__in=[RiskStatus.PENDING, RiskStatus.UNVERIFIED], created_at__lt=cutoff)
        .exclude(Exists(recent_attempt))
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )


def close_abandoned_attempts() -> int:
    """Mark attempts still `running` long after any live call could last as errors.

    Happens when a worker is killed mid-call (deploy, OOM); acks_late redelivers the message, but
    the old row would otherwise claim to be running forever.
    """
    cutoff = timezone.now() - timedelta(seconds=ATTEMPT_SOFT_TIME_LIMIT_SECONDS * 2)
    return RiskCheckAttempt.objects.filter(outcome=AttemptOutcome.RUNNING, started_at__lt=cutoff).update(
        outcome=AttemptOutcome.ERROR,
        finished_at=timezone.now(),
        error_message="abandoned: worker stopped before the registry call finished",
    )


def attempt_outcome_for(assessment: RiskAssessment) -> str:
    return AttemptOutcome.CLEAR if assessment.status == "clear" else AttemptOutcome.FLAGGED


def risk_check_backlog() -> dict[str, Any]:
    """Queue health for /api/status/. A dead worker or beat shows up here as a growing `stale`
    count instead of plots sitting in `pending` with nobody noticing."""
    counts = dict(
        Plot.objects.filter(risk_status__in=[RiskStatus.PENDING, RiskStatus.UNVERIFIED])
        .values_list("risk_status")
        .annotate(n=Count("pk"))
    )
    review_cutoff = timezone.now() - timedelta(days=settings.RISK_CHECK_MANUAL_REVIEW_DAYS)
    stale = len(stale_plot_ids())
    return {
        "pending": counts.get(RiskStatus.PENDING, 0),
        "unverified": counts.get(RiskStatus.UNVERIFIED, 0),
        "stale": stale,
        "requires_manual_review": Plot.objects.filter(
            risk_status=RiskStatus.UNVERIFIED, created_at__lte=review_cutoff
        ).count(),
        "last_attempt_at": RiskCheckAttempt.objects.aggregate(t=Max("started_at"))["t"],
        "healthy": stale == 0,
    }
```

### apps/registry/tasks.py

```python
"""Background deforestation-risk checks.

Flow: POST /api/plots/ -> on commit -> run_risk_check.delay(plot_id) -> worker calls the
registry -> plot becomes clear/flagged. Transient failures retry with exponential backoff and
jitter; when retries run out the plot becomes `unverified` and the periodic sweeper retries later.
"""

import logging

from celery import Task, shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings

from . import services
from .clients import RegistryError, RegistryTimeout, get_registry_client
from .models import Plot, RiskStatus

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    acks_late=True,
    autoretry_for=(RegistryError,),
    # Countdown before retry n is random(0, min(60 * 2**n, 3600)) seconds: 60 s, 120 s, 240 s ...
    # capped at 1 h. Eight retries span up to ~3 h (~1.5 h on average with full jitter), which
    # rides out a typical registry outage; the sweeper covers anything longer.
    retry_backoff=settings.RISK_CHECK_BACKOFF_SECONDS,
    retry_backoff_max=3600,
    retry_jitter=True,
    max_retries=settings.RISK_CHECK_MAX_RETRIES,
    # Backstop above the client's own timeout so a hung call can't pin a worker forever.
    soft_time_limit=services.ATTEMPT_SOFT_TIME_LIMIT_SECONDS,
)
def run_risk_check(self: Task, plot_id: int) -> str:
    plot = Plot.objects.filter(pk=plot_id).first()
    if plot is None:
        logger.warning("risk_check.plot_missing", extra={"plot_id": plot_id})
        return "missing"
    # Idempotent: duplicate deliveries of this message (acks_late, sweeper) are harmless.
    if plot.risk_status in services.SETTLED_STATUSES:
        logger.info("risk_check.skipped", extra={"plot_id": plot_id, "risk_status": plot.risk_status})
        return plot.risk_status

    attempt = services.start_attempt(plot, task_id=self.request.id or "")
    log_ctx = {"plot_id": plot_id, "attempt": attempt.attempt_number, "retries": self.request.retries}
    try:
        try:
            assessment = get_registry_client().check_plot(
                plot_code=plot.plot_code, latitude=plot.latitude, longitude=plot.longitude
            )
        except SoftTimeLimitExceeded:
            # The client ignored its own timeout; record it as a timeout and retry like one.
            raise RegistryTimeout(
                f"registry call exceeded the {services.ATTEMPT_SOFT_TIME_LIMIT_SECONDS}s task time limit"
            ) from None
    except RegistryError as exc:
        services.finish_attempt(attempt, outcome=exc.outcome, error_message=str(exc))
        logger.info(
            "risk_check.attempt",
            extra={**log_ctx, "outcome": exc.outcome, "duration_ms": attempt.duration_ms, "error": str(exc)},
        )
        if self.max_retries is not None and self.request.retries >= self.max_retries:
            services.mark_unverified(plot)
            logger.warning("risk_check.exhausted", extra={**log_ctx, "risk_status": RiskStatus.UNVERIFIED})
            return RiskStatus.UNVERIFIED
        raise  # autoretry_for schedules the next attempt with backoff + jitter

    outcome = services.attempt_outcome_for(assessment)
    services.finish_attempt(attempt, outcome=outcome)
    services.apply_assessment(plot, assessment)
    logger.info(
        "risk_check.attempt",
        extra={**log_ctx, "outcome": outcome, "duration_ms": attempt.duration_ms, "reference": assessment.reference},
    )
    return plot.risk_status


@shared_task
def requeue_stale_risk_checks() -> int:
    """Celery beat job: re-enqueue plots stuck in pending/unverified so hours-long registry
    outages (or a missed enqueue during a broker outage) recover without a human. It also
    closes attempts left `running` by a worker that died mid-call, so the audit trail stays true."""
    abandoned = services.close_abandoned_attempts()
    plot_ids = services.stale_plot_ids()
    queued = sum(services.enqueue_risk_check(plot_id) for plot_id in plot_ids)
    logger.info(
        "risk_check.requeue_stale",
        extra={"found": len(plot_ids), "queued": queued, "abandoned_attempts": abandoned},
    )
    return queued
```

### apps/registry/urls.py

```python
from rest_framework.routers import SimpleRouter

from .views import FarmerViewSet, PlotViewSet, WashingStationViewSet

router = SimpleRouter(trailing_slash=True)
router.register("farmers", FarmerViewSet, basename="farmer")
router.register("plots", PlotViewSet, basename="plot")
router.register("stations", WashingStationViewSet, basename="station")

urlpatterns = router.urls
```

### apps/registry/validators.py

```python
import re

# MTN (078/079) and Airtel (072/073) mobile numbers, in local or international form.
_RW_PHONE = re.compile(r"^(?:\+?250|0)(7[2389]\d{7})$")


def normalise_rwandan_phone(raw: str) -> str | None:
    """Return the E.164 form (+2507XXXXXXXX) of a Rwandan mobile number, or None if invalid."""
    match = _RW_PHONE.match(re.sub(r"[\s-]", "", raw))
    return f"+250{match.group(1)}" if match else None
```

### apps/registry/views.py

```python
from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.policies import Resource
from apps.core.idempotency import NaturalKeyReplayMixin

from . import services
from .filters import PlotFilter
from .models import Farmer, Plot, WashingStation
from .serializers import FarmerSerializer, PlotSerializer, RiskCheckAttemptSerializer, WashingStationSerializer


def _replay_responses(serializer: type) -> dict[int, Any]:
    return {
        201: serializer,
        200: OpenApiResponse(serializer, description="Identical resend: the existing record is returned."),
        409: OpenApiResponse(description="Natural key already registered with different details."),
    }


@extend_schema(methods=["POST"], responses=_replay_responses(FarmerSerializer))
class FarmerViewSet(
    NaturalKeyReplayMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Registering the same member_number again with identical details replays (200).

    Field agents see their station's farmers: anyone with a plot there, or registered there."""

    serializer_class = FarmerSerializer
    natural_key_field = "member_number"
    policy_resource = Resource.FARMERS

    def get_queryset(self) -> QuerySet[Farmer]:
        return Farmer.objects.visible_to(self.request.user).select_related("home_station")

    def find_replay(self, data: dict[str, Any]) -> Farmer | None:
        return services.find_farmer_replay(data, self.get_queryset())

    def replay_mismatches(self, existing: Farmer, data: dict[str, Any]) -> list[str]:  # type: ignore[override]
        return services.farmer_replay_mismatches(existing, data)


@extend_schema(methods=["POST"], responses=_replay_responses(PlotSerializer))
class PlotViewSet(
    NaturalKeyReplayMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Registering a plot returns 201 immediately with `risk_status: "pending"`; the
    deforestation-risk check runs in the background (see apps/registry/tasks.py). Resending the
    same plot_code with identical details replays (200) and does not queue a second check."""

    serializer_class = PlotSerializer
    filterset_class = PlotFilter
    natural_key_field = "plot_code"
    policy_resource = Resource.PLOTS

    def find_replay(self, data: dict[str, Any]) -> Plot | None:
        return services.find_plot_replay(data, self.get_queryset())

    def replay_mismatches(self, existing: Plot, data: dict[str, Any]) -> list[str]:  # type: ignore[override]
        return services.plot_replay_mismatches(existing, data)

    def get_queryset(self) -> QuerySet[Plot]:
        return Plot.objects.visible_to(self.request.user).select_related("sector", "washing_station")

    @extend_schema(responses=RiskCheckAttemptSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="risk-checks", pagination_class=None, filterset_class=None)
    def risk_checks(self, request: Request, pk: str | None = None) -> Response:
        """Every registry call made for this plot, oldest first: evidence of retries."""
        # get_object() starts from the scoped queryset, so another station's plot is a 404.
        plot = self.get_object()
        attempts = plot.risk_checks.order_by("attempt_number")
        return Response(RiskCheckAttemptSerializer(attempts, many=True).data)


class WashingStationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WashingStationSerializer
    pagination_class = None
    policy_resource = Resource.STATIONS

    def get_queryset(self) -> QuerySet[WashingStation]:
        return WashingStation.objects.visible_to(self.request.user).select_related("sector")
```

### tests/conftest.py

```python
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Role, UserProfile
from apps.registry.models import Farmer, Plot, RiskStatus, Sector, WashingStation

STAFF_PASSWORD = "GraderPass123!"


@pytest.fixture(autouse=True)
def _fast_registry(settings: Any) -> None:
    """Never sleep for real in tests, and never run Celery tasks inline by accident."""
    settings.RISK_REGISTRY_MIN_LATENCY = 0
    settings.RISK_REGISTRY_MAX_LATENCY = 0
    settings.CELERY_TASK_ALWAYS_EAGER = False
    # Every API test creates a staff user; real PBKDF2 hashing would dominate the suite's runtime.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def anon_api() -> APIClient:
    """No credentials: only /api/status/, /api/price-schedule/ and the auth endpoints answer."""
    return APIClient()


@pytest.fixture
def make_staff_user(db: None) -> Callable[..., User]:
    """A user with a role profile; field agents default to the Nyaruguru station."""

    def _make(role: str | None, *, station: WashingStation | None = None, username: str | None = None) -> User:
        user = User.objects.create_user(username=username or f"{role or 'no_role'}_user", password=STAFF_PASSWORD)
        if role is not None:
            if role == Role.FIELD_AGENT and station is None:
                station = WashingStation.objects.get(name="Nyaruguru")
            UserProfile.objects.create(user=user, role=role, washing_station=station)
        return User.objects.select_related("profile__washing_station").get(pk=user.pk)

    return _make


def _client_for(user: User) -> APIClient:
    # force_authenticate skips the session/token lookup, so query-count tests measure the view
    # alone. tests/test_auth.py drives real session and token authentication end to end.
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def agent_api(make_staff_user: Callable[..., User]) -> APIClient:
    return _client_for(make_staff_user(Role.FIELD_AGENT))


@pytest.fixture
def kamonyi_agent_api(make_staff_user: Callable[..., User], kamonyi: WashingStation) -> APIClient:
    return _client_for(make_staff_user(Role.FIELD_AGENT, station=kamonyi, username="kamonyi_agent"))


@pytest.fixture
def exporter_api(make_staff_user: Callable[..., User]) -> APIClient:
    return _client_for(make_staff_user(Role.EXPORTER_PARTNER))


@pytest.fixture
def auditor_api(make_staff_user: Callable[..., User]) -> APIClient:
    return _client_for(make_staff_user(Role.COMPLIANCE_AUDITOR))


@pytest.fixture
def nyaruguru(db: None) -> WashingStation:
    return WashingStation.objects.get(name="Nyaruguru")


@pytest.fixture
def kamonyi(db: None) -> WashingStation:
    return WashingStation.objects.get(name="Kamonyi")


@pytest.fixture
def kigoma(db: None) -> Sector:
    return Sector.objects.get(name="Kigoma")


@pytest.fixture
def make_farmer(db: None) -> Callable[..., Farmer]:
    counter = iter(range(1, 10_000))

    def _make(**overrides: Any) -> Farmer:
        n = next(counter)
        fields = {
            "full_name": f"Farmer {n}",
            "member_number": f"KWA-F-T{n:04d}",
            "phone": f"+25078{n:07d}",
        }
        fields.update(overrides)
        return Farmer.objects.create(**fields)

    return _make


@pytest.fixture
def make_plot(
    db: None, make_farmer: Callable[..., Farmer], kigoma: Sector, nyaruguru: WashingStation
) -> Callable[..., Plot]:
    counter = iter(range(1, 10_000))

    def _make(**overrides: Any) -> Plot:
        n = next(counter)
        fields: dict[str, Any] = {
            "farmer": overrides.pop("farmer", None) or make_farmer(),
            "plot_code": f"KWA-P-T{n:04d}",
            "sector": kigoma,
            "washing_station": nyaruguru,
            "latitude": Decimal("-2.540000"),
            "longitude": Decimal("29.710000"),
            "area_hectares": Decimal("0.42"),
            "risk_status": RiskStatus.PENDING,
        }
        fields.update(overrides)
        return Plot.objects.create(**fields)

    return _make


@pytest.fixture
def farmer_payload() -> dict[str, Any]:
    return {
        "full_name": "Uwimana Béatrice",
        "member_number": "KWA-F-0417",
        "cooperative": "Huye",
        "national_id": "1198770123456789",
        "phone": "+250780000000",
    }


@pytest.fixture
def plot_payload(make_farmer: Callable[..., Farmer], nyaruguru: WashingStation) -> dict[str, Any]:
    return {
        # Registered at Nyaruguru, so the default field agent may give this farmer a plot.
        "farmer": make_farmer(home_station=nyaruguru).pk,
        "plot_code": "KWA-P-0417-A",
        "sector": "Kigoma",
        "washing_station": "Nyaruguru",
        "latitude": "-2.540000",
        "longitude": "29.710000",
        "area_hectares": "0.42",
    }


@pytest.fixture
def delivery_payload(make_plot: Callable[..., Plot]) -> dict[str, Any]:
    return {
        "plot": make_plot().pk,
        "washing_station": "Nyaruguru",
        "weight_kg": "38.5",
        "grade": "A",
        "delivered_on": "2026-03-14",
    }
```

