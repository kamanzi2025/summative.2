"""Task 4: the cursor-paginated station delivery feed."""

from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlsplit

import pytest
from django.utils import timezone

from apps.deliveries.models import Delivery
from apps.pricing.models import PriceSchedule
from apps.registry.models import RiskStatus

pytestmark = pytest.mark.django_db

BASE_TIME = timezone.now() - timedelta(days=1)


@pytest.fixture
def make_delivery(make_plot):
    schedule = PriceSchedule.objects.get(is_active=True)
    plots = {}
    counter = iter(range(1, 10_000))

    def _make(station=None, grade="A", risk=RiskStatus.CLEAR, recorded_at=None):
        n = next(counter)
        key = (station.pk if station else None, risk)
        if key not in plots:
            extra = {"washing_station": station} if station else {}
            plots[key] = make_plot(risk_status=risk, **extra)
        plot = plots[key]
        return Delivery.objects.create(
            plot=plot,
            washing_station=plot.washing_station,
            weight_kg=Decimal("30.00"),
            grade=grade,
            client_reference=f"ref-{n}",
            price_schedule=schedule,
            unit_price_rwf=Decimal("760.00"),
            amount_due_rwf=Decimal("22800.00"),
            plot_risk_status_at_delivery=plot.risk_status,
            recorded_at=recorded_at or BASE_TIME + timedelta(minutes=n),
        )

    return _make


def path_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}"


def test_page_shape_and_default_page_size(api, make_delivery):
    for _ in range(25):
        make_delivery()
    body = api.get("/api/deliveries/").json()
    assert set(body) == {"next", "previous", "results"}
    assert len(body["results"]) == 20
    assert "cursor=" in body["next"]
    assert body["previous"] is None
    assert set(body["results"][0]) == {
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
    }


def test_newest_first(api, make_delivery):
    older, newer = make_delivery(), make_delivery()
    ids = [row["id"] for row in api.get("/api/deliveries/").json()["results"]]
    assert ids == [newer.pk, older.pk]


def test_page_size_param_is_capped(api, make_delivery):
    for _ in range(5):
        make_delivery()
    assert len(api.get("/api/deliveries/?page_size=2").json()["results"]) == 2
    # Values above max_page_size are clamped to 100 rather than rejected.
    assert len(api.get("/api/deliveries/?page_size=5000").json()["results"]) == 5


def test_cursor_is_stable_when_new_rows_arrive_between_pages(api, make_delivery):
    """With offset paging, a delivery arriving mid-scroll pushes a row from page 1 onto page 2
    (a duplicate). A cursor continues from the last row actually seen."""
    original = [make_delivery().pk for _ in range(25)]
    page1 = api.get("/api/deliveries/").json()

    make_delivery(recorded_at=timezone.now())  # harvest-peak arrival while the phone is paging

    page2 = api.get(path_of(page1["next"])).json()
    seen = [row["id"] for row in page1["results"]] + [row["id"] for row in page2["results"]]
    assert len(seen) == len(set(seen)), "no delivery appears twice"
    assert sorted(seen) == sorted(original), "no delivery is skipped"
    assert page2["next"] is None


def test_feed_list_runs_one_query(api, make_delivery, django_assert_num_queries):
    for _ in range(20):
        make_delivery()
    # One SELECT with JOINs to plot, farmer and station, regardless of page size (no N+1).
    with django_assert_num_queries(1):
        response = api.get("/api/deliveries/?page_size=20")
    assert len(response.json()["results"]) == 20


def test_station_feed_scopes_and_counts_queries(api, make_delivery, nyaruguru, kamonyi, django_assert_num_queries):
    mine = [make_delivery(station=nyaruguru).pk for _ in range(3)]
    make_delivery(station=kamonyi)
    # 1 query to resolve the station (404 if unknown) + 1 for the page.
    with django_assert_num_queries(2):
        body = api.get(f"/api/stations/{nyaruguru.pk}/deliveries/").json()
    assert sorted(row["id"] for row in body["results"]) == sorted(mine)


def test_station_feed_unknown_station_is_404(api):
    response = api.get("/api/stations/999999/deliveries/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_since_returns_only_newer_rows(api, make_delivery):
    old = make_delivery(recorded_at=BASE_TIME)
    new = make_delivery(recorded_at=BASE_TIME + timedelta(hours=2))
    since = (BASE_TIME + timedelta(hours=1)).isoformat()
    ids = [row["id"] for row in api.get("/api/deliveries/", {"since": since}).json()["results"]]
    assert ids == [new.pk]
    assert old.pk not in ids


def test_grade_and_risk_filters(api, make_delivery):
    a_clear = make_delivery(grade="A", risk=RiskStatus.CLEAR)
    b_clear = make_delivery(grade="B", risk=RiskStatus.CLEAR)
    flagged = make_delivery(grade="A", risk=RiskStatus.FLAGGED)

    def ids(query: str) -> set[int]:
        return {row["id"] for row in api.get(f"/api/deliveries/?{query}").json()["results"]}

    assert ids("grade=B") == {b_clear.pk}
    assert ids("risk_status=flagged") == {flagged.pk}
    assert ids("grade=A&risk_status=clear") == {a_clear.pk}
