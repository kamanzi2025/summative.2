"""Django settings for the Kawa Network API.

Every deploy-specific value comes from the environment (or a local `.env` file created from
`.env.example`). Defaults are safe for local development with SQLite and no Redis.
"""

from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

# --- Core -----------------------------------------------------------------------------------

DJANGO_ENV: str = env("DJANGO_ENV", default="development").strip().lower()
if DJANGO_ENV not in {"development", "production"}:
    raise ImproperlyConfigured("DJANGO_ENV must be either 'development' or 'production'.")
IS_PRODUCTION = DJANGO_ENV == "production"

SECRET_KEY: str = env("SECRET_KEY", default="django-insecure-local-dev-only-change-me")
DEBUG: bool = env.bool("DEBUG", default=False)
_ALLOWED_HOSTS_VALUE = env("ALLOWED_HOSTS", default=None)
ALLOWED_HOSTS: list[str] = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost", "testserver"])
CSRF_TRUSTED_ORIGINS: list[str] = env.list("CSRF_TRUSTED_ORIGINS", default=[])


def _is_https_origin(origin: str) -> bool:
    parsed_origin = urlsplit(origin)
    return (
        parsed_origin.scheme == "https"
        and bool(parsed_origin.netloc)
        and parsed_origin.path in {"", "/"}
        and not parsed_origin.query
        and not parsed_origin.fragment
    )


if IS_PRODUCTION:
    if (
        len(SECRET_KEY.strip()) < 50
        or SECRET_KEY.startswith("django-insecure-")
        or SECRET_KEY.strip().lower() in {"change-me", "replace-with-a-private-random-secret"}
    ):
        raise ImproperlyConfigured("Production requires a non-placeholder SECRET_KEY of at least 50 characters.")
    if DEBUG:
        raise ImproperlyConfigured("DEBUG must be False when DJANGO_ENV is production.")
    if _ALLOWED_HOSTS_VALUE is None or not _ALLOWED_HOSTS_VALUE.strip() or not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        raise ImproperlyConfigured("Production requires an explicit ALLOWED_HOSTS list without wildcards.")
    if any(not _is_https_origin(origin) for origin in CSRF_TRUSTED_ORIGINS):
        raise ImproperlyConfigured("Production CSRF_TRUSTED_ORIGINS entries must be HTTPS origins.")

# Production assumes a trusted TLS-terminating proxy that overwrites X-Forwarded-Proto and keeps
# the application port private. Never enable this setting when clients can reach Django directly.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if IS_PRODUCTION else None
SECURE_SSL_REDIRECT = IS_PRODUCTION
SESSION_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_SECURE = IS_PRODUCTION
# Enable HSTS only after the public TLS hostname and all subdomain behavior are confirmed.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0) if IS_PRODUCTION else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

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
    # See docs/PERFORMANCE_BENCHMARK.md for reproducible, fixture-specific feed payload measurements.
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

# SQLite by default; set DATABASE_URL=postgres://user:pass@host:5432/kawa for Postgres.
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
