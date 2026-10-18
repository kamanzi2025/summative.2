# Bug Report: Summative

This report records the three seeded staging scenarios and additional pricing defects found while
hardening the Kawa Network API. It distinguishes the original seed collection problem, current
passing regression evidence, and historical claims that cannot be reconstructed.

## Verification record

- Before the changes described in this report update, the last verified full suite was
  `.venv/bin/python -m pytest -q`: **321 passed in 29.11s**. This is a prior result; it does not
  include the logging tests and local checks added afterward.
- A previous full-suite result, before the no-role policy change below, was
  `DATABASE_URL=sqlite:///:memory: .venv/bin/python -m pytest -q`: **328 passed in 21.04s**. It
  included the JSON logging tests, auditor access-matrix assertion, fixture seeder pricing check,
  and default-date consistency check. This is historical evidence, not the latest result. The
  standalone deployment smoke and benchmark under `local_checks/` are run explicitly and are not
  in pytest's configured default test paths.
- The latest isolated full-suite run after the pricing changes was **340 passed in 32.81s**. The exact command was:

  ```bash
  PYTHONDONTWRITEBYTECODE=1 DATABASE_URL=sqlite:///:memory: .venv/bin/python -m pytest -p no:cacheprovider -q
  ```

  It includes the fail-closed policy for
  authenticated users without a valid role, denial tests for their reads and writes at both
  stations, anonymous F1 registration coverage, and the existing assigned-role checks. It also
  includes the pricing regression tests below. It used an in-memory database and disabled bytecode
  and pytest cache writes.
- Focused pricing, delivery and fixture-seeding tests: **50 passed in 3.84s**. Staging tests:
  **3 passed in 2.85s**. Both used the in-memory SQLite test database.
- Ruff lint and formatting checks, mypy, Django system checks, migration consistency, OpenAPI
  validation, and `git diff --check` passed after the final formatting change.
- Before that passing run, the first full-suite run after the policy change had **338 passed and 1
  failed in 20.58s**. The failure was an old field-rule test expecting an authenticated user with
  no role to create a farmer. That test now exercises the still-public anonymous F1 registration
  path instead; the policy behavior was not weakened to satisfy it.
- The three original files under `summative/seed` did not collect in this repository because they
  imported a `core` package that is not present here. The exact collection errors are preserved in
  `docs/evidence/staging_raw_output.txt`. The adapted tests under `tests/staging/` use this
  repository's `apps.*` layout.
- The original staging result was a collection failure, not a recorded failing product assertion.
  No preserved test output demonstrates that the adapted regression tests failed before a fix.
  Where Git history does not show a test preceding a fix, this report makes no test-first claim.

## Staging scenario 1: Coordinate precision across pagination

**Symptom under investigation:** An `exporter_partner` could receive a plot's precise stored
coordinates on a later page even if the first page or detail response were coarsened. Precise plot
coordinates identify a family's land, so the consequence would be a location privacy breach.

**Cause and current protection:** The implementation applies `CoordinateField` to both plot
coordinate fields. That field consults `policy_for(user)` and returns the sector reference point
for `exporter_partner` readers. The same serializer is used for every paginated row, and the cursor
contains ordering position rather than coordinates. The tested path has no page-specific
coarsening branch. The scenario did not establish a current leak.

**Evidence and result:**

- `tests/staging/test_pagination_coarsening.py::test_coarsened_coordinates_hold_on_every_page`
  walks the cursor pages, compares each returned point to the stored plot point, and checks one
  consistent point per sector and distinct points between sectors. It passed in the latest
  verified 340-test run.
- `tests/test_field_rules.py` and `tests/test_sector_reference_points.py` cover the shared field
  rule and sector reference points. They were included in that same passing suite.
- The adapted staging test's comment records its changes from the seed: model imports, foreign key
  lookups, and deriving page size from the configured paginator. It says the assertions and
  scenario volume were preserved.

**Limit:** The serializer rule does not govern code paths that bypass DRF serialization, such as a
future raw query export. The current tests cover the API serializer path.

## Staging scenario 2: Price schedule after a mid-season update

**Symptom under investigation:** A station could continue seeing an old price after a schedule
update. The domain consequence is that a farmer may be quoted a stale farm-gate price.

**Cause and current protection:** `PriceScheduleView.get()` fetches the currently effective
  schedule on each request; there is no server-side cache to invalidate. `Cache-Control` permits a
  client or proxy to reuse a response for up to 60 seconds. Schedules are date-effective, and
  `get_active_schedule()` selects the latest active schedule whose `effective_from` is no later than
  the requested date, across season labels under the project's chosen assumption below. The
  staging test itself updates a schedule within the same season; it does not establish cross-season
  precedence.

**Evidence and result:**

- `tests/staging/test_price_schedule_staleness.py::test_price_schedule_reflects_update_within_documented_window`
  updates through `activate_schedule()`, checks the next GET returns the updated price, and checks
  the 60-second cache header. It passed in the latest verified 340-test run.
- `tests/test_pricing_and_errors.py::test_price_change_is_served_on_next_request` also checks
  that a changed price is read on the next request.

The seed failure mode describes an application that introduces a server-side cache without an
invalidation path. That condition is not present in the current implementation. The initial seed
collection failure and the adapted test's current passing result do not demonstrate that this
repository previously had a stale-cache defect.

## Staging scenario 3: Delivery after a failed risk check

**Symptom:** Before the current implementation update, delivery responses exposed only a boolean
`is_exportable` and the delivery-time risk snapshot. A delivery whose registry check failed did not
explain whether it was held or why. The domain consequence was that station and export users could
not distinguish a pending or unverified delivery from a rejected one, delaying or misdirecting
traceability decisions.

**Cause and current behavior:** The delivery representation had no explanatory export status or
reason. The configured registry URL also lacked a provider contract, so using a simulator result
for a configured URL could have represented an unsupported external clearance. Current delivery
create, detail, and feed representations expose `export_status` and `export_status_reason` from the
plot's current risk status. A non-empty `REGISTRY_API_URL` fails closed with a static error until a
registry contract is supplied; an empty value selects the simulator. Failed checks are retried and
recorded, while delivery recording and payment snapshots do not wait for registry success.

**Evidence and result:**

- `tests/test_risk_check_stranding.py` covers unsupported configured-registry behavior, retry
  attempts, URL secrecy, held status after failure, and response/feed fields. It passed in the
  latest verified 340-test run.
- `tests/staging/test_delivery_risk_check_stranding.py::test_delivery_reaches_an_observable_state_after_failed_risk_check`
  exercises a failed check followed by delivery recording and asserts that the response has a
  status-like field. It passed in the latest run. Its assertion accepts any one of several field names;
  the dedicated tests assert the exact `export_status` and `export_status_reason` contract.
- `tests/test_deliveries.py` and `tests/test_feed.py` cover the create/detail/feed API paths.

The actual provider HTTP integration remains unsupported because its request, authentication, and
response contract has not been supplied. No real registry request was made for these tests.

## Own defect: Future-effective schedule deactivated the current price too early

The earlier `activate_schedule()` implementation deactivated every active schedule in the season
as soon as a replacement was activated, even when the replacement's `effective_from` was in the
future. Until that date, the price endpoint could have no effective schedule and delivery
validation could reject otherwise valid deliveries. This is a farmer payment and intake continuity
defect.

The current implementation retains schedules for distinct effective dates and selects the latest
active schedule effective on the requested date across all season labels. Treating season as a
descriptive label on one global pricing timeline is the project's chosen assumption; the assignment
contracts do not specify cross-season precedence. A database constraint now permits only one
active schedule per effective date globally. Activation rejects same-date schedules from another
season, and the selector fails closed on ambiguous dates. Migration
`apps/pricing/migrations/0004_global_effective_date_uniqueness.py` checks for existing conflicts
before changing the constraint; it does not reconcile or delete schedule data. Evidence is in
`tests/test_pricing_and_errors.py::test_future_schedule_keeps_current_price_until_effective_date`,
`tests/test_pricing_and_errors.py::test_activation_rejects_cross_season_schedule_with_same_effective_date`,
`apps/pricing/services.py`, and migration
`apps/pricing/migrations/0003_schedule_by_effective_date.py`. The tests passed in the latest
340-test run. The prior committed implementation is inspectable in Git history, but no preserved
pre-fix failing-test output establishes test-first chronology.

## Additional pricing defect: Late-synced deliveries used today's price

Before the current change, delivery validation selected a price without passing the delivery date,
so a late sync could select using the server's current date instead of the delivery date. When those
dates fall on opposite sides of a schedule change, this can snapshot the wrong rate and overpay or
underpay a farmer. The current code selects the globally effective schedule for `delivered_on` and
persists the unit-price, amount, and schedule snapshots. The regression test checks a delivery dated
before the update uses the old rate, and deliveries dated on and after a cross-season update use the
new rate. The exact cross-season precedence is a project assumption, not an assignment requirement.

Evidence is in `tests/test_deliveries.py::test_late_synced_delivery_uses_price_effective_on_delivery_date`
and the prior committed serializer implementation in Git history. The regression test passed in the
latest 340-test run. No preserved failing output or commit history demonstrates that this test
existed before the implementation change.

## Other pricing checks

- The 60-second `Cache-Control` lifetime matches the documented client/proxy reuse window; the
  next server request reads the current effective schedule.
- When `delivered_on` is omitted, the serializer captures `timezone.localdate()` once and uses the
  same date for both selection and storage. The effective-date boundary follows `Africa/Kigali`.
- An immediate schedule change takes effect on its date. Existing deliveries retain their stored
  payment snapshots.

These points are covered by the current date-based pricing implementation and tests. Earlier
drafts referred to throwaway probe tests, but no probe files or captured output are preserved, so
those probes are not presented as independent evidence here.

## Additional date-consistency protections

- `tests/test_seed_rbac_fixtures.py::test_seeded_deliveries_use_price_effective_on_the_fixture_delivery_date`
  verifies that the fixed-date F2 fixture gets its price from that fixture date, even when a newer
  schedule is already active by the time it is seeded.
- `tests/test_deliveries.py::test_default_delivery_date_is_the_same_date_used_for_price_selection`
  verifies that an API request omitting `delivered_on` stores the same local date used to select its
  price. The serializer now makes that date explicit before saving, avoiding a midnight-boundary
  mismatch between validation and the model default.
- `tests/test_seed_demo.py::SeedDemoPricingTests::test_seeded_deliveries_use_one_date_for_price_and_delivery`
  verifies that the demo command captures one local date and passes it to both schedule selection
  and delivery recording.

These are current regression assertions. The report does not claim a failing-test-first chronology
for them.

## Broker credential redaction

The broker outage path in `enqueue_risk_check()` logs a warning without the transport exception
text or traceback. `tests/test_logging.py::test_broker_outage_log_does_not_expose_connection_credentials`
injects an exception containing a credential-bearing broker URL and asserts that neither the URL
nor its password appears in captured logs. The full suite's current result includes this test.
