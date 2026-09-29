# Architecture Decision Records

Kawa Network API, Formative 1. Each record states the problem, the decision, the options we
rejected and what the decision costs. Records are append-only: a changed decision gets a new ADR
that supersedes the old one.

| ADR | Decision | Status | Main stakeholder |
|---|---|---|---|
| [ADR-001](#adr-001-accept-then-verify-for-plot-deforestation-risk-checks) | Verify plot risk in the background; never block deliveries on the registry | Accepted | Emmanuel, Jeanne (Patrick carries the cost) |
| [ADR-002](#adr-002-whose-performance-problem-to-solve-first-the-station-delivery-feed) | Cursor-paginate the station delivery feed instead of caching the price schedule | Accepted | Emmanuel |
| [ADR-003](#adr-003-idempotent-writes-keyed-on-natural-identifiers) | Make every create idempotent on the record's natural key | Accepted | Emmanuel, Jeanne |

---

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

Harvest starts in three weeks, and Emmanuel's station at Nyaruguru is the pilot. Three
stakeholders pull in different directions:

- **Emmanuel** wants to **record a delivery in seconds on a bad connection**. At harvest peak his
  station takes about **400 deliveries a day**, entered on a phone over **2G** with a queue of
  farmers watching. He cannot hold a farmer at the weighing scale while the registry thinks, and
  on 2G a request that hangs for 40 seconds usually fails and gets retried.
- **Jeanne** wants **every farmer paid correctly, the same day they deliver**. A farmer who carries
  cherry to the scale cannot be told to come back when a server elsewhere answers, and the cherry
  itself starts to ferment within hours.
- **Patrick** wants **traceability data flowing to buyers before the shipping window closes**.
  Buyers need each lot traced to its plot and that plot shown not to sit on recently cleared land,
  and the registry's verdict is the evidence.

The obvious design is to call the registry while the plot is being registered and refuse
deliveries until the plot is cleared. That puts a slow, unreliable third party at the weighing
scale, which is Emmanuel's queue and Jeanne's payday. It does not even help Patrick: the verdict
arrives no sooner, while deliveries stall behind it.

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
     backoff and full jitter (`retry_backoff=60`, `retry_backoff_max=3600`, `retry_jitter=True`,
     `max_retries=8`). The wait before retry *n* is random between 0 and
     `min(60 × 2ⁿ, 3600)` seconds: up to 1, 2, 4, 8, 16, 32, 60 and 60 minutes. The worst case
     is 10,980 s (about **3 hours**) and the average is about half that. Random spacing stops
     hundreds of plots registered during the same outage from retrying at the same instant.
     `test_retry_schedule_spans_hours_not_minutes` pins this arithmetic.
   - A registry call that ignores its own timeout is stopped by the task's soft time limit. It is
     recorded as a `timeout` attempt and retried like any other timeout.
   - Attempt numbers are allocated under a row lock on the plot and are unique per plot (DB
     constraint), so the audit trail cannot contain two "attempt 3"s.
   - The task is idempotent. If the plot is already `clear` or `flagged`, it does nothing, so a
     redelivered message (`acks_late=True`) or a duplicate enqueue is harmless.
   - When the retries run out, the plot becomes `unverified` and a warning is logged.
3. A Celery beat job, `requeue_stale_risk_checks`, runs every 15 minutes. It re-enqueues plots
   that have been `pending` or `unverified` for more than `RISK_CHECK_STALE_HOURS` (6 hours) with
   no recent attempt. The 6-hour window is longer than the whole retry chain, so the sweeper
   never competes with a chain that is still running. An outage longer than the retry budget
   therefore recovers without a person stepping in. The same job also catches plots whose enqueue
   failed because Redis was down. It also closes attempts left `running` by a worker that was
   killed mid-call, recording them as errors, so the history never claims a call is still in
   progress.
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

- This breaks Jeanne's requirement of same-day pay. During a multi-hour outage, every new plot's
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
- Every delivery keeps its provenance chain (delivery → plot → farmer, sector and station) from the
  first day of harvest, with a snapshot of the risk status at the time it was accepted. When
  Patrick sends data to buyers, it is complete and shows exactly what was known when.
- Each retry leaves evidence in `RiskCheckAttempt`, and `GET /api/plots/{id}/risk-checks/`
  exposes it.
- Outages recover on their own through backoff, then the stale-check sweeper.

### Negative

- **Operational complexity.** We now run Redis, a Celery worker and Celery beat, and we have to
  monitor them. A dead worker means plots stay `pending`. The sweeper, the
  `risk_check.*` log events and the `risk_checks` backlog on `/api/status/` (`stale` count,
  `healthy` flag) make that visible to monitoring, but someone still has to act on the alert.
- **Eventual consistency.** A plot's status can be `pending` for minutes, or for hours during an
  outage. Every consumer of plot data must treat `pending` and `unverified` as "not yet known",
  never as "OK".
- **Patrick carries the cost of registry outages.** A plot that is still `pending` or `unverified`
  cannot contribute to an export lot, so a long outage just before the shipping window can hold
  back traceability data he needs. We limit this rather than eliminate it:
  - **Register plots before harvest.** Plots can be registered in the three weeks before harvest
    starts, so their checks can finish (with up to about 3 hours of retries, plus the sweeper)
    before the first delivery arrives. Only plots first seen at the scale depend on the registry
    during harvest.
  - Nothing has to be re-entered. When a plot clears, all of its earlier deliveries become
    exportable automatically.
  - Stuck plots are visible early (`?requires_manual_review=true`), not discovered the week the
    ship leaves.
- **We will pay for cherry we may not be able to export.** If a plot is later `flagged`, the
  cooperative has already paid for its cherry. This is a deliberate business trade-off (see the
  policy below).
- **Duplicate registry calls are still possible**, for example when a worker dies after calling the
  registry but before acknowledging the message (`acks_late` redelivers it). They are harmless,
  because the task skips settled plots and attempt numbers stay unique, but they cost registry
  quota.

## Stakeholder impact

| Stakeholder | Wants (from the brief) | Impact of this decision |
|---|---|---|
| **Emmanuel** | To record a delivery in seconds on a bad connection | **Benefits most.** The decision removes the registry from the one moment he cannot afford to wait: the farmer at the scale. Registration and deliveries return in milliseconds on 2G. Safe retries (`client_reference`) mean a dropped connection never creates a double delivery, and a reused reference with different values is refused (`409`) rather than silently answered with the wrong delivery. |
| **Jeanne** | Every farmer paid correctly, the same day | **Benefits strongly.** No delivery is ever refused or delayed because of the registry, and the price is snapshotted when the delivery is recorded, so same-day pay is correct even if prices change later or the registry is down all day. |
| **Patrick** | Traceability data flowing to buyers before the shipping window closes | **Mixed. He pays the main cost.** Provenance is complete from the first delivery, and cleared plots flow straight into exportable data. But cherry from unchecked plots is held back until the registry answers. The mitigations above (pre-harvest registration, automatic release when a plot clears, and review queues for stuck and flagged plots) exist to keep that delay away from the shipping window. |

**Why Emmanuel over Jeanne:** the brief places the registry problem at Emmanuel's scale ("Emmanuel
cannot hold a farmer at the weighing scale while it runs"), and that is exactly the step this
decision unblocks. Jeanne's same-day pay depends on that step too, but she also relies on the
price snapshot, which is a separate design choice.

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
   Jeanne requires same-day pay. These deliveries are non-exportable. They are listed at
   `GET /api/deliveries/?exportable=false&risk_status=flagged` so the people preparing buyer data
   can keep them out of traceable lots and decide what happens to that cherry (for example,
   selling it outside the traceable channel).
5. **Retries continue after `unverified`.** `unverified` means "no answer", not a verdict. The
   beat sweeper keeps re-enqueuing the check every `RISK_CHECK_STALE_HOURS`.
6. **Manual review after N days.** A plot still `unverified` after
   `RISK_CHECK_MANUAL_REVIEW_DAYS` (default 7) shows `requires_manual_review: true` and appears
   in the queue `GET /api/plots/?requires_manual_review=true`. Someone then checks it by hand
   (site visit or an alternative data source) before its cherry can enter an export lot, so
   Patrick hears about a stuck plot weeks before the shipping window rather than during it.

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
  which Emmanuel reads on 2G. It **grows by about 400 rows a day** at the pilot station during
  harvest peak.
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
- **`?since=` has a small blind spot.** `recorded_at` is stamped when the row is written, not when
  its transaction commits. A delivery whose write is slow can therefore become visible with a
  timestamp slightly *older* than one the phone has already seen, and a strict `since` poll would
  skip it. Clients poll with a 2-minute overlap (`since = newest recorded_at − 120 s`) and
  de-duplicate by `id`. The cost is a few repeated rows per poll, which is far cheaper than a
  missing payment line. A server-side sequence assigned at commit would remove the blind spot
  entirely; it is deferred until the feed has more than one writer per station.
- **The index is proven, not assumed.** `EXPLAIN` on the feed query shows
  `SEARCH deliveries_delivery USING INDEX delivery_station_feed_idx (washing_station_id=? AND recorded_at<?)`
  with no sort step, and `test_station_feed_query_uses_composite_index` fails if that regresses.
- If the price schedule ever becomes a hot path, a server-side cache can be added then, with
  invalidation on save. We have deferred it on purpose.

---

# ADR-003: Idempotent writes keyed on natural identifiers

- **Status:** Accepted
- **Date:** 2026-09-29
- **Scope:** `POST /api/farmers/`, `POST /api/plots/`, `POST /api/deliveries/`

## Context

Station phones talk to the API over 2G. A common failure is not "the request never arrived" but
"the request succeeded and the response was lost". The phone cannot tell these apart, so it
resends. Without protection:

- A resent **delivery** records the same cherry twice, and Jeanne pays the farmer twice.
- A resent **farmer** or **plot** registration fails with a duplicate-key `400`. The clerk sees
  an error for something that worked, and may re-enter it with a typo to get past the error.
- A resent **plot** would also queue a second registry check (ADR-001).

Each resource already has an identifier the station knows before it sends the request: a
farmer's `member_number`, a plot's `plot_code`, and, for deliveries, a `client_reference` the phone
generates per weighing (unique per station).

## Decision

**Every create is idempotent on that natural key.** Before validation, the view looks the key up:

1. **No match:** create normally and return `201` with `Idempotent-Replayed: false`.
2. **Match with an identical body** (after the same normalisation the serializer applies, e.g.
   phone numbers to E.164 and `"38.5"` equal to `"38.50"`): return the stored record with `200`
   and `Idempotent-Replayed: true`. Nothing is written, and no risk check is queued.
3. **Match with a different body:** return `409 conflict` with
   `details: {"id", "mismatched_fields"}`, so the phone can show what differs.

A race between two identical requests that both pass step 1 is caught by the database unique
constraint and answered with the original record. The logic lives in one place,
`NaturalKeyReplayMixin` (`apps/core/idempotency.py`), so all three endpoints behave and document
the same way. The replay check runs *before* validation on purpose: a delivery replayed after a
price change must return what was originally recorded, not fail or re-price.

## Alternatives considered

- **`Idempotency-Key` request header with a stored response.** The general-purpose industry
  pattern. Rejected for F1: it needs a key/response store with expiry, and the station app would
  have to generate and keep a second identifier alongside the natural key it already has.
  It stays the right option if a create without a natural key appears.
- **Rely on unique constraints and return `400`.** Simplest, but it turns every successful retry
  into an error the clerk has to interpret, and it gives no protection to deliveries, whose
  natural fields (plot, weight, grade, day) can legitimately repeat.
- **De-duplicate deliveries on (plot, weight, grade, date).** Rejected: two identical 35 kg
  deliveries from the same plot on the same day are real and must both be paid.

## Consequences

- **Positive:** retries are always safe, so the phone can retry aggressively on a bad connection.
  No duplicate payments, no false errors, no duplicate registry calls.
- **Negative:** the station app must generate a unique `client_reference` per delivery.
  Without one, deliveries are not protected (the field is optional in F1 for the contract's
  sake). Replay comparison is hand-written per resource and must track serializer changes;
  `tests/test_farmers.py`, `tests/test_plots.py` and `tests/test_deliveries.py` cover equivalent
  and conflicting resends to catch drift.
- **Security note for F2:** a replay currently returns the stored record to anyone who knows the
  natural key. Once authentication lands, replays must go through the same object-level
  permission check as `GET` on that record.
