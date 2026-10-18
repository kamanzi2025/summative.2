"""Structured logging contract and sensitive-data regression coverage."""

import json
import logging
from decimal import Decimal

import pytest
from kombu.exceptions import OperationalError

from apps.core.logging import JsonFormatter
from apps.deliveries.services import record_delivery
from apps.pricing.models import PriceSchedule
from apps.registry.models import RiskStatus
from apps.registry.services import enqueue_risk_check
from apps.registry.tasks import run_risk_check

pytestmark = pytest.mark.django_db


def test_json_formatter_preserves_event_and_structured_context():
    record = logging.LogRecord("apps.registry.tasks", logging.INFO, __file__, 20, "risk_check.attempt", (), None)
    record.plot_id = 42
    record.attempt = 2

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "risk_check.attempt"
    assert payload["logger"] == "apps.registry.tasks"
    assert payload["level"] == "INFO"
    assert payload["plot_id"] == 42
    assert payload["attempt"] == 2
    assert payload["ts"]


def test_application_json_logs_omit_coordinates_national_id_and_registry_credentials(
    caplog, make_farmer, make_plot, monkeypatch
):
    latitude = Decimal("-2.123456")
    longitude = Decimal("29.654321")
    national_id = "1199000012345678"
    credential = "private-log-token"
    farmer = make_farmer(national_id=national_id)
    plot = make_plot(
        farmer=farmer,
        latitude=latitude,
        longitude=longitude,
        risk_status=RiskStatus.PENDING,
    )
    schedule = PriceSchedule.objects.get(is_active=True)

    caplog.set_level(logging.INFO)
    record_delivery(
        plot=plot,
        washing_station=plot.washing_station,
        weight_kg=Decimal("10.00"),
        grade="A",
        price_entry=schedule.entries.get(grade="A"),
    )

    # Configured URLs fail closed; this task exercises the same call path that receives the
    # plot's precise coordinates, while ensuring its log context stays identifier-only.
    from django.test import override_settings

    monkeypatch.setattr(run_risk_check, "max_retries", 0)
    with override_settings(REGISTRY_API_URL=f"https://user:{credential}@registry.invalid/check"):
        result = run_risk_check.apply(args=[plot.pk])
    assert result.get() == RiskStatus.UNVERIFIED

    application_records = [
        record
        for record in caplog.records
        if record.name in {"apps.deliveries.services", "apps.registry.tasks", "celery.app.trace"}
    ]
    rendered = [JsonFormatter().format(record) for record in application_records]
    payloads = [json.loads(line) for line in rendered]

    assert any(payload["event"] == "delivery.recorded" for payload in payloads)
    assert any(payload["event"] == "risk_check.attempt" for payload in payloads)
    combined = "\n".join(rendered)
    for sensitive_value in (str(latitude), str(longitude), national_id, credential):
        assert sensitive_value not in combined


def test_broker_failure_log_omits_connection_credentials(caplog, monkeypatch):
    broker_url = "redis://service-user:private-broker-password@redis.example.invalid:6379/0"

    def fail_publish(plot_id):
        raise OperationalError(f"could not connect to {broker_url} for plot {plot_id}")

    monkeypatch.setattr("apps.registry.tasks.run_risk_check.delay", fail_publish)
    caplog.set_level(logging.INFO, logger="apps.registry.services")

    assert enqueue_risk_check(17) is False

    records = [record for record in caplog.records if record.name == "apps.registry.services"]
    rendered = "\n".join(JsonFormatter().format(record) for record in records)
    assert any(record.getMessage() == "risk_check.enqueue_failed" for record in records)
    assert "private-broker-password" not in rendered
    assert broker_url not in rendered
