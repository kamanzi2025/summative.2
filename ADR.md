# ADR-001: Accept-then-verify for plot deforestation-risk checks

- **Status:** Accepted
- **Date:** 2026-09-29
- **Deciders:** Kawa Network backend (F1)
- **Scope:** Plot registration, delivery recording, the risk-check worker, and what happens to
  cherry from plots the registry has not cleared

## Context

Kawa Network buys coffee cherry from smallholder farmers at washing stations such as Nyaruguru.
Every export lot must trace back to the land the coffee grew on, and buyers need to know that the
land was not recently deforested. That verdict comes from an **external deforestation-risk
registry**.

The registry does not behave like a local service:

- A single check takes anywhere from about **2 to 40 seconds**.
- It has **outages that last hours**, not seconds.
- We do not control it, and we cannot make it faster.

Meanwhile, the people using our API work under tight constraints:

- **Jeanne (farmer liaison, farmer-facing):** farmers must be **paid the same day** they deliver.
  A farmer who walks cherry to the scale cannot be told to come back when a server in another
  country answers. Cherry also starts to ferment within hours, so it cannot wait either.
- **Emmanuel (station manager, Nyaruguru):** registers plots and records deliveries from a phone
  on a **2G connection**, where a request that hangs for 40 seconds usually fails and gets retried.
  During the harvest peak his station records around **400 deliveries a day**.
- **Patrick (compliance/export):** needs a reliable, auditable answer to "which lots can we sell as
  deforestation-free?" and a record of what was known when each delivery was accepted.

The obvious design is to call the registry while the plot is being registered and refuse
deliveries until the plot is cleared. That puts a slow, unreliable third party directly in the
path of a farmer being paid.

## Decision

**Accept-then-verify: plot risk verification is an asynchronous, retried background status on the
plot, decoupled from delivery recording; deliveries are never blocked by the external registry,
and provenance + risk status are snapshotted per delivery.**

Concretely:

1. `POST /api/plots/` saves the plot with `risk_status = "pending"` and returns `201` straight
   away. The risk check is queued with
   `transaction.on_commit(lambda: enqueue_risk_check(plot.pk))`, so a worker never sees a plot
   row that has not been committed. The registry is never called inside a web request
   (`apps/registry/services.py`).
2. A Celery worker runs `run_risk_check(plot_id)` (`apps/registry/tasks.py`):
   - Each call to the registry creates a `RiskCheckAttempt` row with the start time, end time,
     duration, outcome (`clear | flagged | error | timeout`), error message and Celery task id.
     This table is the audit trail showing the retries really happened.
   - Transient failures (`RegistryUnavailable`, `RegistryTimeout`) are retried with exponential
     backoff and full jitter (`retry_backoff=True`, `retry_backoff_max=3600`, `retry_jitter=True`,
     `max_retries=8`). This spreads roughly 4 hours of retries across the fleet instead of
     hammering a registry that is already down.
   - The task is idempotent. If the plot is already `clear` or `flagged`, it does nothing, so a
     redelivered message (`acks_late=True`) or a duplicate enqueue is harmless.
   - When the retries run out, the plot becomes `unverified` and a warning is logged.
3. A Celery beat job, `requeue_stale_risk_checks`, runs every 15 minutes. It re-enqueues plots
   that have been `pending` or `unverified` for more than `RISK_CHECK_STALE_HOURS` (6 hours) with
   no recent attempt. An outage longer than the retry budget therefore recovers without a person
   stepping in. The same job also catches plots whose enqueue failed because Redis was down.
4. `POST /api/deliveries/` accepts cherry from a plot **whatever its risk status**. The
   delivery records the plot, which is the provenance link. It also snapshots:
   - `unit_price_rwf` and `amount_due_rwf`, from the price schedule active at recording time
   - `plot_risk_status_at_delivery`, which records what we knew when we accepted the cherry
5. Export eligibility is computed, never stored. `is_exportable` is true only while the delivery's
   plot is currently `clear`. When a pending plot clears later, its earlier deliveries become
   exportable automatically.

## Alternatives considered

### A. Synchronous check at plot registration

Call the registry inside `POST /api/plots/` and return the verdict in the response.

- Registration would take 2 to 40 seconds and fail outright during an outage. On Emmanuel's 2G
  connection, requests that long time out on the client side. The phone then retries, which
  doubles the load on a registry that is already struggling.
- Each slow request ties up a web worker. On a busy registration day, a registry outage becomes an
  outage of *our* API.
- **Rejected:** it makes our availability equal to the registry's.

### B. Block deliveries until the plot is cleared

Check asynchronously, but reject `POST /api/deliveries/` while the plot is not `clear`.

- This breaks Jeanne's hard rule of same-day pay. During a multi-hour outage, every new plot's
  farmer would be turned away at the scale, and the cherry would spoil.
- It pushes stations to work around the system (paper records, recording cherry against someone
  else's cleared plot). That destroys the traceability the check exists to protect.
- **Rejected:** it protects exports by harming farmers, and it weakens provenance in practice.

### C. Synchronous check with a short timeout and a fallback

Try the registry for about 3 seconds during registration, and fall back to `pending` if it does
not answer.

- Most calls (2 to 40 s) would hit the fallback anyway, so we would still need all the async
  machinery, plus a slow code path in the request.
- **Rejected:** it has the complexity of both designs and the benefits of neither.

## Consequences

### Positive

- Plot registration and delivery recording respond in milliseconds and never depend on the
  registry being up.
- Farmers are always paid the same day, at the price in force that day. Later price changes never
  rewrite what a farmer was owed.
- Every delivery keeps its provenance chain (delivery → plot → farmer) and a snapshot of the risk
  status at the time it was accepted, so Patrick can audit exactly what was known when.
- Each retry leaves evidence in `RiskCheckAttempt`, and `GET /api/plots/{id}/risk-checks/`
  exposes it.
- Outages recover on their own through backoff, then the stale-check sweeper.

### Negative

- **Operational complexity.** We now run Redis, a Celery worker and Celery beat, and we have to
  monitor them. A dead worker means plots stay `pending` quietly. The sweeper and
  `risk_check.*` log events reduce this risk but do not remove it.
- **Eventual consistency.** A plot's status can be `pending` for minutes, or for hours during an
  outage. Every consumer of plot data must treat `pending` and `unverified` as "not yet known",
  never as "OK".
- **We will pay for cherry we may not be able to export.** If a plot is later `flagged`, the
  cooperative has already paid for its cherry. This is a deliberate business trade-off (see the
  policy below).
- **Duplicate registry calls are possible** in rare races, for example a sweeper requeue that
  overlaps a late retry. They are harmless, because the task skips settled plots, but they cost
  registry quota.

## Stakeholder impact

| Stakeholder | Impact |
|---|---|
| **Jeanne** (farmer liaison) | **Benefits most.** Deliveries are never refused because of the registry, and pay is priced and snapshotted at the scale, so the same-day pay rule holds even during a registry outage. |
| **Emmanuel** (station manager) | Plot registration and deliveries return immediately on 2G. Safe retries (`client_reference`) mean a dropped connection never creates a double delivery. He can filter his feed by `risk_status` to see which deliveries still need a verdict. |
| **Patrick** (compliance/export) | Gets a clear rule (only currently `clear` plots are exportable), a per-delivery snapshot, and a full attempt history. In return, he has to manage a review queue for `flagged` plots and long-`unverified` ones. |

## Non-functional requirements

| NFR | Effect |
|---|---|
| **Availability** | *Helped.* Our write paths no longer depend on the registry, and a Redis outage does not fail registration either: the enqueue failure is logged and the sweeper recovers the plot. |
| **Latency on 2G** | *Helped.* Registration and delivery requests do one or two small DB writes. There is no 2 to 40 second wait on a fragile connection. |
| **Data integrity / traceability** | *Helped.* Deliveries must reference a plot, and the station must equal the plot's station. Price and risk are snapshotted, and DB constraints enforce uniqueness and value ranges. *Stressed* by eventual consistency: exports must check the current status, never the snapshot alone. |
| **Operational complexity** | *Stressed.* Redis, worker and beat are three more moving parts to deploy, monitor and secure. They are documented in the README and wired in `docker-compose.yml`. |

## Plots whose risk check never succeeds

Some registry checks will fail for a very long time, or permanently. The policy for those plots:

1. **Deliveries are still accepted.** Deliveries from `pending` and `unverified` plots are
   recorded and paid the same day. We never block the farmer at the scale.
2. **Every delivery snapshots `plot_risk_status_at_delivery`**, so the record always shows that the
   cherry was accepted before a verdict existed.
3. **Not exportable until cleared.** Lots from plots that are not `clear` are excluded from buyer
   traceability exports. `is_exportable` is `false` until the plot becomes `clear`, and then it
   flips to `true` for all of that plot's deliveries.
4. **Flagged plots:** deliveries are still recorded and paid. The cherry is physically there, and
   Jeanne's rule is same-day pay. These deliveries are marked non-exportable and surfaced for
   review (`GET /api/deliveries/?risk_status=flagged`).
5. **Retries continue after `unverified`.** `unverified` means "no answer", not a verdict. The
   beat sweeper keeps re-enqueuing the check every `RISK_CHECK_STALE_HOURS`.
6. **Manual review after N days.** A plot still `unverified` after
   `RISK_CHECK_MANUAL_REVIEW_DAYS` (default 7) shows `requires_manual_review: true`. Compliance
   then checks it by hand (site visit or an alternative data source) before its cherry can enter
   an export lot.

---

# ADR-002: Whose performance problem to solve first: the station delivery feed

- **Status:** Accepted
- **Date:** 2026-09-29

## Context

Task 4 asks for one assessed performance feature: either pagination or caching. Two endpoints
were candidates:

- `GET /api/price-schedule/`: **a few hundred bytes**, the same for everyone, and it changes a
  few times a season.
- The station delivery feed (`GET /api/deliveries/`, `GET /api/stations/{id}/deliveries/`),
  which Emmanuel reads on 2G. It **grows by about 400 rows a day per station** at harvest peak.
  New rows arrive at the top *while he is scrolling*.

## Decision

Solve **Emmanuel's feed first**, using **cursor pagination** ordered by `(-recorded_at, -id)`.
The ordering is backed by the composite index `Delivery(washing_station, -recorded_at, -id)`.
Supporting choices:

- A default page of 20 rows, adjustable with `?page_size=` up to a maximum of 100.
- A slim, flat feed serializer with no nested objects. A measured page of 20 rows is
  **6,316 bytes** (about 315 bytes a row), and `GZipMiddleware` sends it as **832 bytes** on the
  wire.
- `select_related("plot__farmer", "washing_station")`, so one page is **one SQL query** however
  many rows it has. A test asserts this with `django_assert_num_queries`.
- `?since=<ISO datetime>`, so the phone fetches only rows newer than the ones it already holds.

**Why cursor over offset:** with `?page=2`, a delivery recorded between two page loads pushes a row
from page 1 onto page 2. Emmanuel sees it twice, and when rows are removed or re-filtered he can
miss one. `OFFSET n` also makes the database walk and discard `n` rows, so each later page gets
slower as the season's table grows. A cursor says "continue after this position". It reads only
the index range it needs, and it is stable under inserts. A test inserts a row between pages and
asserts nothing is duplicated or skipped.

**Why not caching the price schedule as the assessed feature:** caching a few-hundred-byte payload
that almost never changes saves very little, and it adds an invalidation problem on the one
endpoint where a stale answer means paying a farmer the wrong price. The price endpoint still
sends `Cache-Control: public, max-age=60`, and it has no server-side cache, so a price change is
visible to the next request and to every client within 60 seconds.

## Consequences

- The feed has no total count and no "jump to page 7". Station staff scroll newest-first and never
  need either, and skipping `COUNT(*)` is part of the saving.
- The cursor is opaque, so clients must follow the `next` link rather than build URLs themselves.
- If the price schedule ever becomes a hot path, a server-side cache can be added then, with
  invalidation on save. We have deferred it on purpose.
