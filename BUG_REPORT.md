# Bug Report: Summative

This report covers the three staging scenarios from `summative/seed` and the defects found while
hardening the Kawa Network API for the Nyaruguru rollout. Each entry follows
`docs/templates/BUG_REPORT_TEMPLATE.md`.

## Staging scenarios at a glance

The seed tests could not run as delivered. They import a `core` package that this project does
not have, so all three failed at collection. The raw output is in
`docs/evidence/staging_raw_output.txt`. I ported each test to this project's layout without
weakening any assertion; each file starts with a comment listing exactly what changed.

| # | Scenario | Test | Result after porting |
|---|---|---|---|
| 1 | Coordinate precision under pagination | `tests/staging/test_pagination_coarsening.py` | **Passes.** An F1/F2 decision prevents the fault (below). |
| 2 | Stale price schedule after a mid-season update | `tests/staging/test_price_schedule_staleness.py` | **Passes.** An F1 decision prevents the fault (below). |
| 3 | Delivery stranded on a failed risk check | `tests/staging/test_delivery_risk_check_stranding.py` | **Fails.** A genuine defect, diagnosed and fixed below. |

To show that the two passing tests are not vacuous, I re-ran each one with the protecting code
disabled in memory. Each then failed, with the messages quoted below.

---

## Scenario 1: Coordinate precision under pagination (passes)

### Bug Summary

The scenario asks whether an exporter partner walking every page of `GET /api/plots/` ever
receives a plot's stored coordinates instead of the coarsened ones. It catches implementations
that coarsen in one code path, such as the first page or the detail view, and miss others.

### Why It Matters

Exporter partners must see location only at sector precision (F2 access matrix). Exact plot
coordinates identify a family's land. A leak on page 2 is still a leak.

### Why the fault cannot happen here: the F2 decisions that prevent it

1. **Coarsening is a property of the field, not of a view or page.** `CoordinateField` in
   `apps/accounts/field_rules.py` overrides `get_attribute()`. When the reader's policy says
   `CoordinatePrecision.SECTOR`, it returns `instance.sector.reference_latitude/longitude`
   instead of the plot's own value. `PlotSerializer` declares `latitude` and `longitude` as
   `CoordinateField`s, so every serialisation of a plot goes through it: list pages, detail,
   nested plots, and the response to a create. Pagination only decides *which rows* are
   serialised, never *how*.
2. **One central policy decides precision.** `policy_for(user)` in
   `apps/accounts/policies.py` maps `exporter_partner` to `CoordinatePrecision.SECTOR`. Views
   never test role names, so no view can forget.
3. **A fixed reference point per sector, not rounding.** Every plot in a sector reports the same
   point, chosen so that no rounding of a real plot coordinate reaches it (migration
   `registry/0010`, DECISION_LOG.md "Coordinate precision by role"). This is why the test's
   "one consistent point per sector" and "different sectors, different points" assertions hold.
4. **Cursor pagination leaks no coordinates.** The cursor encodes only a position in
   `(-created_at, -id)` (`apps/core/pagination.py`), and `PlotFilter` offers no coordinate
   filters or ordering. A caller therefore cannot narrow down a plot's location by filtering or
   sorting.
5. **A guard against new leaks.** `tests/test_field_rules.py` fails if a serializer exposes a
   protected field without its rule.

### Regression Evidence

- `tests/staging/test_pagination_coarsening.py` passes. It walks 3 pages (44 plots, page size
  20), and every row is coarsened.
- **Sabotage check:** with `CoordinateField.get_attribute` replaced in memory by plain
  `DecimalField.get_attribute`, the test fails:
  `plot KWA-STAGING-039 on page 1 returned its raw stored coordinate to exporter_partner instead of a coarsened one`.
- Existing coverage: `tests/test_field_rules.py`, `tests/test_sector_reference_points.py`.

### Residual Risk

- Anything that bypasses DRF serializers would bypass the rule: the Django admin, a future CSV
  export, or raw `values()` queries. Only staff can reach the admin today.
- The reference point reveals the sector, by design. A sector with a single plot would let an
  exporter tie that plot to the sector, which is no finer than the policy allows.

---

## Scenario 2: Stale price schedule after a mid-season update (passes)

### Bug Summary

The scenario asks whether, after the price schedule is updated mid-season, `GET /api/price-schedule/`
serves the new price within the invalidation window the README documents. It catches F1
implementations that added a cache with no invalidation path.

### Why It Matters

The price schedule is what a field agent reads out to a farmer at the scale. A stale price means
a farmer is told, or paid, the wrong amount.

### Why the fault cannot happen here: the F1 decisions that prevent it

1. **No server-side cache, on purpose.** `PriceScheduleView.get()` in
   `apps/pricing/views.py` calls `get_active_schedule()` (`apps/pricing/services.py`) on every
   request, which is one indexed query over a handful of rows. ADR.md records the trade-off:
   caching a tiny table saves almost nothing, and it adds an invalidation problem on the one
   endpoint where staleness costs a farmer money. With no cache, there is nothing to invalidate.
2. **Prices are database rows with one active schedule per season.** A mid-season change is a
   new `PriceSchedule` activated by `activate_schedule()`. That function is atomic, and the DB
   constraint `one_active_schedule_per_season` guarantees there is never more than one candidate.
3. **Delivery pricing never uses a cached value.** `DeliverySerializer.validate()` calls
   `get_active_price(grade)` when each delivery is recorded. `record_delivery()` then stores
   `unit_price_rwf`, `amount_due_rwf` and the `price_schedule` foreign key on the delivery, so a
   later change never rewrites what a farmer was paid.
4. **The client-side window is explicit and documented.** The response carries
   `Cache-Control: public, max-age=60` (`PRICE_SCHEDULE_MAX_AGE_SECONDS`). README "Cache
   invalidation" says a client or proxy may show the old price for at most 60 seconds.

### Regression Evidence

- `tests/staging/test_price_schedule_staleness.py` passes. The very next GET after
  `activate_schedule()` serves the new grade-A price, and the header is `max-age=60`.
- **Sabotage check:** with an F1-style memoising cache (no invalidation) wrapped around
  `get_active_schedule` in the view, the test fails:
  `expected 797.00, got 760.00`.

### Residual Risk

- For up to 60 s after a change, a phone or proxy may display the old price while a delivery
  recorded in that window is priced (correctly) at the new one. This is documented and bounded,
  but the farmer could briefly see a different figure on screen than on the receipt.
- See "Price edge cases investigated" below for the two date-related defects found while checking
  this scenario.

---

## Scenario 3: Delivery stranded on a failed risk check (fails: open)

### Bug Summary

When the deforestation-risk registry never answers for a plot, deliveries from that plot carry no
export status and no reason. The ported test fails on its unchanged assertion: the response has
none of `status`, `state`, `export_status`, `risk_check_status` or `rejection_reason`. It only has
`is_exportable: false` and the risk status as it was at delivery time.

Root cause, fix and regression evidence follow in this entry once the fix lands (Summative
Step 4). Until then the staging test is marked `xfail(strict=True)` so that CI stays green.

---

## Price edge cases investigated

These were checked with throwaway probe tests against a migrated test database (freezing
`timezone.now()` where time mattered). I did not change any code to check them.

| Edge case | Finding | Verdict |
|---|---|---|
| `Cache-Control: max-age=60` vs README wording | The README says a client or proxy may show old prices for **at most 60 seconds**, and the header is `public, max-age=60`. A compliant shared cache sends `Age`, so the client and proxy together still stay within 60 s. | **Accurate. Not a bug.** |
| "Already in effect" with dates vs datetimes, `TIME_ZONE`/`USE_TZ` | Every "today" in the price and delivery code is `timezone.localdate()`, which uses `TIME_ZONE = "Africa/Kigali"`. At 22:30 UTC on 14 Oct it returns **15 Oct** (00:30 in Kigali), and a schedule effective 15 Oct applies. `effective_from` is a `DateField`, so no datetime is ever compared against it. There is no `date.today()` or `now().date()` anywhere. | **Correct. Not a bug.** Prices switch at Kigali midnight. |
| Two schedules switching mid-day | `activate_schedule()` flips `is_active` in one transaction. A delivery recorded one minute after activation gets the **new** price (900 vs the old 760 in the probe). Deliveries recorded before activation keep their snapshot. Activation is immediate because `effective_from` is date-granular. | **Behaves as designed.** |
| Activating a **future-dated** schedule in the same season | `activate_schedule()` deactivates the current schedule at once, but the new one only counts from its `effective_from`. Until then **no schedule is in effect**: `GET /api/price-schedule/` returns **404** and every delivery is rejected with "No active price for grade A". | **Real defect** (confirmed by probe). |
| Back-dated delivery (`delivered_on` in the past) | `DeliverySerializer.validate()` prices with `get_active_price(grade)`, i.e. **today's** price, not the price in effect on `delivered_on`. A delivery made yesterday at 760 RWF/kg but synced from a 2G phone after today's switch is recorded at 900 RWF/kg. | **Real defect**, if the rule is "the farmer is paid the price of the delivery day" (the farm-gate price is paid at the scale). |

Which of these is fixed, and how, is recorded in the "Own defect" entry below.
