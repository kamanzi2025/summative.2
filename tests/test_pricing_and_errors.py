import datetime

import pytest
from django.db import IntegrityError, transaction

from apps.pricing.models import PriceSchedule
from apps.pricing.services import activate_schedule

pytestmark = pytest.mark.django_db


def test_price_schedule_shape_and_cache_header(api):
    response = api.get("/api/price-schedule/")
    assert response.status_code == 200
    assert response.json() == {
        "id": PriceSchedule.objects.get(is_active=True).pk,
        "season": "2026A",
        "effective_from": "2026-03-01",
        "currency": "RWF",
        "unit": "kg",
        "prices": [
            {"grade": "A", "price_per_kg_rwf": "760.00"},
            {"grade": "B", "price_per_kg_rwf": "500.00"},
            {"grade": "C", "price_per_kg_rwf": "300.00"},
        ],
    }
    assert "max-age=60" in response.headers["Cache-Control"]


def test_price_change_is_served_on_next_request(api):
    api.get("/api/price-schedule/")
    PriceSchedule.objects.get(is_active=True).entries.filter(grade="A").update(price_per_kg_rwf="800.00")
    prices = api.get("/api/price-schedule/").json()["prices"]
    assert prices[0] == {"grade": "A", "price_per_kg_rwf": "800.00"}


def test_no_active_schedule_is_404(api):
    PriceSchedule.objects.update(is_active=False)
    response = api.get("/api/price-schedule/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_only_one_active_schedule_per_season():
    with pytest.raises(IntegrityError), transaction.atomic():
        PriceSchedule.objects.create(season="2026A", effective_from=datetime.date(2026, 5, 1), is_active=True)


def test_activate_schedule_deactivates_previous():
    old = PriceSchedule.objects.get(is_active=True)
    new = PriceSchedule.objects.create(season="2026A", effective_from=datetime.date(2026, 5, 1))
    activate_schedule(new)
    old.refresh_from_db()
    assert not old.is_active and new.is_active


def test_validation_error_envelope(api):
    response = api.post("/api/farmers/", {}, format="json")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "The request data is invalid."
    assert error["details"]["full_name"] == ["This field is required."]


def test_not_found_envelope(api):
    response = api.get("/api/farmers/999999/")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "No Farmer matches the given query.", "details": {}}
    }


def test_method_not_allowed_envelope(api):
    response = api.delete("/api/price-schedule/")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_malformed_json_envelope(api):
    response = api.post("/api/farmers/", "{not json", content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "parse_error"
