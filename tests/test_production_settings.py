from __future__ import annotations

import os
import subprocess
import sys


def _settings_process(extra_environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DJANGO_ENV": "production",
            "SECRET_KEY": "test-only-" + "s" * 64,
            "DEBUG": "False",
            "ALLOWED_HOSTS": "api.example.test",
            "CSRF_TRUSTED_ORIGINS": "",
            "DATABASE_URL": "sqlite:///:memory:",
        }
    )
    environment.update(extra_environment)
    script = """
import django
try:
    django.setup()
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}")
    raise SystemExit(1)
from django.conf import settings
print("DJANGO_ENV=" + settings.DJANGO_ENV)
print("DEBUG=" + str(settings.DEBUG))
print("ALLOWED_HOSTS=" + ",".join(settings.ALLOWED_HOSTS))
print("SECURE_SSL_REDIRECT=" + str(settings.SECURE_SSL_REDIRECT))
print("SESSION_COOKIE_SECURE=" + str(settings.SESSION_COOKIE_SECURE))
print("CSRF_COOKIE_SECURE=" + str(settings.CSRF_COOKIE_SECURE))
print("SECURE_PROXY_SSL_HEADER=" + str(settings.SECURE_PROXY_SSL_HEADER))
print("CSRF_TRUSTED_ORIGINS=" + ",".join(settings.CSRF_TRUSTED_ORIGINS))
print("SECURE_HSTS_SECONDS=" + str(settings.SECURE_HSTS_SECONDS))
print("STATIC_ROOT=" + str(settings.STATIC_ROOT))
"""
    return subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        text=True,
    )


def test_production_requires_non_placeholder_secret_without_echoing_it() -> None:
    for invalid_secret in ("", "change-me"):
        result = _settings_process({"SECRET_KEY": invalid_secret})
        assert result.returncode != 0
        assert "Production requires a non-placeholder SECRET_KEY" in result.stdout
        if invalid_secret:
            assert invalid_secret not in result.stdout + result.stderr


def test_production_requires_explicit_non_wildcard_hosts() -> None:
    for invalid_hosts in ("", "*"):
        result = _settings_process({"ALLOWED_HOSTS": invalid_hosts})
        assert result.returncode != 0
        assert "Production requires an explicit ALLOWED_HOSTS" in result.stdout


def test_production_rejects_debug_and_non_https_csrf_origins() -> None:
    debug_result = _settings_process({"DEBUG": "True"})
    assert debug_result.returncode != 0
    assert "DEBUG must be False" in debug_result.stdout

    for invalid_origin in ("http://api.example.test", "https://"):
        csrf_result = _settings_process({"CSRF_TRUSTED_ORIGINS": invalid_origin})
        assert csrf_result.returncode != 0
        assert "CSRF_TRUSTED_ORIGINS entries must be HTTPS origins" in csrf_result.stdout


def test_valid_production_configuration_enables_proxy_aware_security() -> None:
    result = _settings_process({"CSRF_TRUSTED_ORIGINS": "https://api.example.test"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DJANGO_ENV=production" in result.stdout
    assert "DEBUG=False" in result.stdout
    assert "ALLOWED_HOSTS=api.example.test" in result.stdout
    assert "SECURE_SSL_REDIRECT=True" in result.stdout
    assert "SESSION_COOKIE_SECURE=True" in result.stdout
    assert "CSRF_COOKIE_SECURE=True" in result.stdout
    assert "SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https')" in result.stdout
    assert "CSRF_TRUSTED_ORIGINS=https://api.example.test" in result.stdout
    assert "SECURE_HSTS_SECONDS=0" in result.stdout
    assert "STATIC_ROOT=" in result.stdout and "/staticfiles" in result.stdout


def test_production_target_forces_production_mode_over_runtime_environment() -> None:
    project_root = os.path.dirname(os.path.dirname(__file__))
    dockerfile = open(os.path.join(project_root, "Dockerfile"), encoding="utf-8").read()
    production_target = dockerfile.split("FROM app-base AS production", maxsplit=1)[1].split(
        "FROM app-base AS development", maxsplit=1
    )[0]
    assert 'ENTRYPOINT ["sh", "/app/docker/production-entrypoint.sh"]' in production_target

    environment = os.environ.copy()
    environment.update(
        {
            "DJANGO_ENV": "development",
            "SECRET_KEY": "test-only-" + "s" * 64,
            "DEBUG": "False",
            "ALLOWED_HOSTS": "api.example.test",
            "DATABASE_URL": "sqlite:///:memory:",
        }
    )
    result = subprocess.run(
        [
            "sh",
            os.path.join(project_root, "docker", "production-entrypoint.sh"),
            sys.executable,
            "-c",
            "import django; django.setup(); from django.conf import settings; "
            "print(settings.DJANGO_ENV); print(settings.SESSION_COOKIE_SECURE)",
        ],
        check=False,
        capture_output=True,
        cwd=project_root,
        env=environment,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "production" in result.stdout.splitlines()
    assert "True" in result.stdout.splitlines()


def test_development_mode_keeps_local_security_defaults() -> None:
    result = _settings_process(
        {
            "DJANGO_ENV": "development",
            "SECRET_KEY": "local-development-test-key",
            "DEBUG": "True",
            "ALLOWED_HOSTS": "localhost,127.0.0.1",
        }
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DJANGO_ENV=development" in result.stdout
    assert "DEBUG=True" in result.stdout
    assert "SECURE_SSL_REDIRECT=False" in result.stdout
    assert "SESSION_COOKIE_SECURE=False" in result.stdout
    assert "CSRF_COOKIE_SECURE=False" in result.stdout
    assert "SECURE_PROXY_SSL_HEADER=None" in result.stdout
