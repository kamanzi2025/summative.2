"""Reproducible, single-session HTTP benchmark for the station harvest feed.

This measures the local Django development server and in-memory SQLite test database. It is not a
concurrent-capacity or production-database benchmark; see docs/PERFORMANCE_BENCHMARK.md.
"""

import json
import math
import platform
import statistics
import time
from datetime import timedelta
from decimal import Decimal
from urllib.request import Request, urlopen

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from pytest_django.live_server_helper import LiveServer
from rest_framework.authtoken.models import Token

from apps.accounts.models import Role, UserProfile
from apps.deliveries.models import Delivery
from apps.pricing.models import PriceSchedule
from apps.registry.models import Farmer, Plot, RiskStatus, Sector, WashingStation


@pytest.mark.django_db(transaction=True)
def test_single_agent_harvest_feed_benchmark(live_server: LiveServer) -> None:
    initial_count = 400
    page_size = 20
    harvest_window = timedelta(hours=8)
    interval_seconds = harvest_window.total_seconds() / initial_count
    station = WashingStation.objects.get(name="Nyaruguru")
    plot = Plot.objects.create(
        farmer=Farmer.objects.create(
            full_name="Benchmark farmer",
            member_number="KWA-BENCHMARK-1",
            phone="+250780000001",
            home_station=station,
        ),
        plot_code="KWA-P-BENCHMARK-1",
        sector=Sector.objects.get(name="Kigoma"),
        washing_station=station,
        area_hectares=Decimal("0.42"),
        latitude=Decimal("-2.540000"),
        longitude=Decimal("29.710000"),
        risk_status=RiskStatus.CLEAR,
    )
    schedule = PriceSchedule.objects.get(is_active=True)
    start = timezone.now() - timedelta(days=2)
    deliveries = [
        Delivery(
            plot=plot,
            washing_station=station,
            weight_kg=Decimal("30.00"),
            grade="A",
            client_reference=f"benchmark-{index:04d}",
            price_schedule=schedule,
            unit_price_rwf=Decimal("760.00"),
            amount_due_rwf=Decimal("22800.00"),
            plot_risk_status_at_delivery=RiskStatus.CLEAR,
            recorded_at=start + timedelta(seconds=index * interval_seconds),
        )
        for index in range(initial_count)
    ]
    Delivery.objects.bulk_create(deliveries)
    expected_ids = {delivery.pk for delivery in Delivery.objects.filter(client_reference__startswith="benchmark-")}

    user = User.objects.create_user(username="feed_benchmark_agent", password="benchmark-only")
    UserProfile.objects.create(user=user, role=Role.FIELD_AGENT, washing_station=station)
    token = Token.objects.create(user=user)
    headers = {"Authorization": f"Token {token.key}"}

    url = f"{live_server.url}/api/deliveries/?page_size={page_size}"
    latencies_ms: list[float] = []
    page_sizes_bytes: list[int] = []
    observed_ids: list[int] = []
    inserted_arrival_id = None

    while url:
        request = Request(url, headers=headers)
        started = time.perf_counter()
        with urlopen(request, timeout=10) as response:
            raw_body = response.read()
            assert response.status == 200
        latencies_ms.append((time.perf_counter() - started) * 1000)
        page_sizes_bytes.append(len(raw_body))
        page = json.loads(raw_body)
        observed_ids.extend(row["id"] for row in page["results"])

        if inserted_arrival_id is None:
            arrival = Delivery.objects.create(
                plot=plot,
                washing_station=station,
                weight_kg=Decimal("30.00"),
                grade="A",
                client_reference="benchmark-arrival-during-scroll",
                price_schedule=schedule,
                unit_price_rwf=Decimal("760.00"),
                amount_due_rwf=Decimal("22800.00"),
                plot_risk_status_at_delivery=RiskStatus.CLEAR,
                recorded_at=start + harvest_window + timedelta(seconds=1),
            )
            inserted_arrival_id = arrival.pk
        url = page["next"]

    assert len(latencies_ms) == math.ceil(initial_count / page_size)
    assert len(observed_ids) == initial_count
    assert len(set(observed_ids)) == initial_count
    assert set(observed_ids) == expected_ids
    assert inserted_arrival_id not in observed_ids

    compressed_request = Request(
        f"{live_server.url}/api/deliveries/?page_size={page_size}",
        headers={**headers, "Accept-Encoding": "gzip"},
    )
    with urlopen(compressed_request, timeout=10) as response:
        compressed_page_bytes = len(response.read())
        assert response.headers.get("Content-Encoding") == "gzip"

    ordered = sorted(latencies_ms)
    p95_ms = ordered[math.ceil(0.95 * len(ordered)) - 1]
    result = {
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "workload": {
            "initial_deliveries": initial_count,
            "harvest_window_hours": harvest_window.total_seconds() / 3600,
            "arrival_interval_seconds": interval_seconds,
            "concurrent_agent_sessions": 1,
            "page_size": page_size,
            "new_delivery_inserted_after_first_page": True,
            "database": "pytest temporary SQLite test database",
            "transport": "HTTP over loopback to Django live_server",
        },
        "measurement": {
            "pages": len(latencies_ms),
            "response_bytes_first_page_uncompressed": page_sizes_bytes[0],
            "response_bytes_first_page_gzip": compressed_page_bytes,
            "page_latency_ms_median": round(statistics.median(latencies_ms), 3),
            "page_latency_ms_p95": round(p95_ms, 3),
            "page_latency_ms_max": round(max(latencies_ms), 3),
            "all_initial_deliveries_seen_once": True,
            "mid_scroll_arrival_excluded_from_cursor_walk": True,
        },
    }
    print(f"FEED_BENCHMARK_RESULT {json.dumps(result, sort_keys=True)}")
