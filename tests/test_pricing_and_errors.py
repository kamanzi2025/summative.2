import datetime

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import Conflict
from apps.pricing.models import PriceEntry, PriceSchedule
from apps.pricing.services import activate_schedule, get_active_price, get_active_schedule

pytestmark = pytest.mark.django_db


def test_price_schedule_shape_and_cache_header(anon_api):
    response = anon_api.get("/api/price-schedule/")
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


def test_price_change_is_served_on_next_request(anon_api):
    anon_api.get("/api/price-schedule/")
    PriceSchedule.objects.get(is_active=True).entries.filter(grade="A").update(price_per_kg_rwf="800.00")
    prices = anon_api.get("/api/price-schedule/").json()["prices"]
    assert prices[0] == {"grade": "A", "price_per_kg_rwf": "800.00"}


def test_no_active_schedule_is_404(anon_api):
    PriceSchedule.objects.update(is_active=False)
    response = anon_api.get("/api/price-schedule/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_only_one_active_schedule_per_effective_date_globally():
    current = PriceSchedule.objects.get(is_active=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        PriceSchedule.objects.create(season="2026B", effective_from=current.effective_from, is_active=True)


def test_activation_rejects_cross_season_schedule_with_same_effective_date():
    current = PriceSchedule.objects.get(is_active=True)
    duplicate_date = PriceSchedule.objects.create(season="2026B", effective_from=current.effective_from)

    with pytest.raises(Conflict, match="same effective date"):
        activate_schedule(duplicate_date)

    current.refresh_from_db()
    duplicate_date.refresh_from_db()
    assert current.is_active is True
    assert duplicate_date.is_active is False
    assert get_active_schedule(on=current.effective_from).pk == current.pk


def test_future_schedule_keeps_current_price_until_effective_date():
    old = PriceSchedule.objects.get(is_active=True)
    today = timezone.localdate()
    future = today + datetime.timedelta(days=10)
    new = PriceSchedule.objects.create(season="2026B", effective_from=future)
    PriceEntry.objects.bulk_create(
        PriceEntry(schedule=new, grade=entry.grade, price_per_kg_rwf=entry.price_per_kg_rwf + 10)
        for entry in old.entries.all()
    )
    activate_schedule(new)
    old.refresh_from_db()
    assert old.is_active and new.is_active
    assert get_active_schedule(on=today).pk == old.pk
    assert get_active_schedule(on=future).pk == new.pk
    assert get_active_price("A", on=today).schedule_id == old.pk
    assert get_active_price("A", on=future).schedule_id == new.pk


def test_validation_error_envelope(agent_api):
    response = agent_api.post("/api/farmers/", {}, format="json")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "The request data is invalid."
    assert error["details"]["full_name"] == ["This field is required."]


def test_not_found_envelope(agent_api):
    response = agent_api.get("/api/farmers/999999/")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "No Farmer matches the given query.", "details": {}}
    }


def test_method_not_allowed_envelope(anon_api):
    response = anon_api.delete("/api/price-schedule/")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_malformed_json_envelope(agent_api):
    response = agent_api.post("/api/farmers/", "{not json", content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "parse_error"
