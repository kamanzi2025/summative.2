# Delivery feed benchmark

## Reproduction

From the repository root, with the declared dependencies installed in `.venv`, run:

```sh
PYTHONDONTWRITEBYTECODE=1 DATABASE_URL=sqlite:///:memory: .venv/bin/python -m pytest -p no:cacheprovider -q -s local_checks/performance/test_delivery_feed_benchmark.py
```

The standalone test uses pytest's temporary SQLite test database, runs Django's live test server
on loopback, and measures each sequential `GET /api/deliveries/?page_size=20` request. It creates
400 initial deliveries, then inserts one newer delivery after the first response while the client
continues through the cursor pages. It checks that every initial row appears exactly once and the
new row does not shift into the in-progress cursor walk. It separately measures the first-page
response body with and without `Accept-Encoding: gzip`.

The workload is an explicit synthetic assumption: one station, one authenticated field-agent
session, 400 deliveries distributed evenly over an eight-hour shift (50 per hour, one every 72
seconds), twenty rows per page, and one arrival during scrolling. **Concurrency is one session.**
The repository's approximate 400-per-day volume does not establish actual peak concurrency; this
benchmark makes no claim about simultaneous agents or production capacity.

## Measurement method and historical measurements

The test starts its timing immediately before `urllib.request.urlopen()` and stops after the
response body is read. It gathers 20 page timings, reports `statistics.median`, computes p95 by
the nearest-rank index `ceil(0.95 * n) - 1` in the sorted observations, and reports the maximum
observation. Startup, migrations, and fixture creation are outside the timed interval. The raw
size is `len(response.read())` for a request without `Accept-Encoding`; the compressed size is the
body length returned by the same local HTTP server when the request sends `Accept-Encoding: gzip`
and the response has `Content-Encoding: gzip`. Thus compression is measured over HTTP by Django's
configured `GZipMiddleware`, not estimated offline.

ADR-002 retains an earlier report of **6,316 raw bytes / 832 gzip bytes**. Its data fixture and
measurement procedure are not specified closely enough here to establish that it used the same
records, response fields, request headers, or timing method as this benchmark. The current run
uses 20 rows from a synthetic 400-delivery dataset and the current response shape. Keep both
measurements with their provenance; do not treat the size difference as a directly comparable
performance trend until those conditions are matched.

## Recorded results

The latest run on Python 3.12.3, macOS 12.7.6 x86_64, with the local Django test server and
temporary SQLite database produced:

| Measure | Result |
|---|---:|
| Page requests | 20 |
| Median page response | 15.934 ms |
| 95th percentile page response | 20.686 ms |
| Maximum observed page response | 625.165 ms |
| First-page JSON body, uncompressed | 8,774 bytes |
| First-page JSON body, gzip | 726 bytes |
| Initial deliveries returned once | Yes |
| Mid-scroll arrival included in cursor walk | No |

These are measurements from one local run, not service-level targets. The maximum is reported
alongside the median and percentile rather than omitted. Timing includes local HTTP, Django
middleware, API serialization, and SQLite work; it excludes database/server startup and the
benchmark's fixture creation. The body sizes are the measured response bytes for this test's data
and current response fields. They are not a production payload guarantee. No arbitrary latency
threshold is used.

Repeated local runs using this benchmark have recorded gzip body sizes of **684, 699, 707, 747, and
726 bytes**, while the raw page body remained **8,774 bytes**. The compressed size depends on the
response content, including runtime-generated timestamps; it is an observation for each run, not
a fixed size guarantee. The table above records the latest run only.

This is a single-session workflow benchmark, not a concurrent load test. It does not exercise
PostgreSQL, Redis/Celery, external registry services, a production web server, remote network
latency, or production hardware. Repeat it on the intended deployment stack and with an
operator-supplied concurrency profile before making capacity claims.
