<!-- REPO_SNAPSHOT part 4 of 4. Paste all parts in order. -->

# REPO SNAPSHOT (part 4 of 4, continued)

## 5. SUMMARY

**Authentication.** Configured in `config/settings.py` → `REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]`:
1. `apps.accounts.authentication.TokenOrBearerAuthentication`: DRF `TokenAuthentication` that also accepts `Authorization: Bearer <key>`
2. `rest_framework.authentication.SessionAuthentication`
3. `rest_framework.authentication.BasicAuthentication`

Login endpoints are in `apps/accounts/views.py` and `apps/accounts/urls.py` (`/api/auth/staff-login/` for sessions, `/api/auth/api-token/` for tokens).

**Role-based access.**
- **Rules:** all of them live in `apps/accounts/policies.py`. That file holds `ROLE_POLICIES` for field_agent, exporter_partner and compliance_auditor, plus `NO_ROLE_POLICY` for logged-in users with no profile and `ANONYMOUS_POLICY`, which grants POST on farmers, plots and deliveries and no reads.
- **Endpoint checks:** `apps.accounts.permissions.RolePolicyPermission` is set as `DEFAULT_PERMISSION_CLASSES`. A view must declare `policy_resource` or it is denied. GET/HEAD/OPTIONS need READ; every other method needs WRITE.
- **Row checks:** `StationScopedQuerySet.visible_to(user)` in `apps/accounts/scoping.py` does this, and view querysets start from it. Out-of-scope records return 404.
- **Serializer relations:** `ScopedRelationsMixin` narrows related-field querysets the same way.
- **Public views:** status, price schedule and login set `AllowAny`.

**National-ID masking and coordinate coarsening.** Both are in `apps/accounts/field_rules.py`, at the field level:
- **National ID:** `NationalIdField.to_representation` masks it to `****…6789`, which is what field agents see. For every other role, `PolicyFieldsMixin.get_fields` drops the field from the output; it is still accepted as write-only input.
- **Coordinates:** `CoordinateField.get_attribute` returns `sector.reference_latitude` / `sector.reference_longitude` instead of the stored value when the policy says `SECTOR`. That applies to exporters, no-role users and anonymous callers.
- **Prices:** `CommercialTermField` hides `unit_price_rwf` and `amount_due_rwf` from auditors.

The rules sit on the field classes, not in a list view, so they apply on every page and in nested serializers.

**Audit log.** `apps.audit.middleware.AuditLogMiddleware` is the last entry in `MIDDLEWARE`:
- **When it writes:** after the response, for any view that has a `policy_resource`. This includes 401, 403 and 404 responses.
- **What it writes:** one `AuditLog` row with user, role, method, path, view name, status, resource, returned object ids and the field rules that applied.
- **On failure:** it is not wrapped in try/except, so if the write fails the request returns 500.
- **What it skips:** public views (price schedule, status, login).
- **Who can read it:** only the auditor, at `/api/audit-log/` (`apps/audit/views.py`, `filters.py`, `serializers.py`).

**Async risk check.**
1. `register_plot` calls `transaction.on_commit(enqueue_risk_check)`, which runs `apps.registry.tasks.run_risk_check.delay(plot_id)`. If the broker is down, the error is caught and the plot stays `pending`.
2. The task calls `get_registry_client()`. That always returns `SimulatedRiskRegistry`: `REGISTRY_API_URL` is read in settings but never used (`apps/registry/clients.py:79`).
3. Each attempt is stored as a `RiskCheckAttempt` row.
4. If `RegistryError` is raised, the task retries with exponential backoff and jitter: up to `RISK_CHECK_MAX_RETRIES=8`, base 60 s, capped at 1 h per wait.
5. Once retries run out, the plot becomes **`unverified`**.
6. Celery beat runs `requeue_stale_risk_checks` every 15 min. It re-enqueues plots that are still `pending` or `unverified` after `RISK_CHECK_STALE_HOURS=6`, and closes attempts left `running` by a dead worker.
7. After `RISK_CHECK_MANUAL_REVIEW_DAYS=7`, an unverified plot is counted under `requires_manual_review` in `risk_check_backlog()` (status endpoint).

If the check never succeeds, there is no terminal "rejected" state: the plot stays `unverified` and is retried forever. Deliveries are always accepted. Each one stores `plot_risk_status_at_delivery` and exposes a computed `is_exportable`, which is true only while the plot is `clear`. So a delivery on a never-verified plot just shows `is_exportable: false` with no reason given.

**Delivery price.**
- `DeliverySerializer.validate` calls `apps.pricing.services.get_active_price(grade)`, which queries the DB for the newest active `PriceSchedule` that is already in effect. If no price is found, it returns a 400.
- `apps.deliveries.services.record_delivery` then copies `unit_price_rwf`, `amount_due_rwf` (weight × price, rounded half-up) and the `price_schedule` foreign key onto the delivery.
- **No server-side cache:** neither `GET /api/price-schedule/` (`apps/pricing/views.py`) nor delivery pricing caches anything. Each request reads the DB. The only staleness is the `Cache-Control: public, max-age=60` header (`PRICE_SCHEDULE_MAX_AGE_SECONDS`), which lets clients reuse a response for up to 60 s.
- Switching schedules is done by `activate_schedule()`, backed by a DB constraint that allows one active schedule per season.

**Broken, unfinished or inconsistent.**
1. **`summative/seed` is not merged into main.** It adds `tests/staging/` (4 files). I ran it from a `git archive` export in a temp directory.
2. **All 3 staging tests fail at collection.** They import `core.models` and `core.views`, but this repo uses `apps.core`, `apps.registry` and `apps.pricing`, and there is no `core` package. Fixing the imports alone would not make them pass, because they were written for a different reference implementation:
   - **Pagination test:** calls `Plot.objects.create(sector="Kigoma", washing_station="Nyaruguru")` with strings, but here those are foreign keys to `Sector` and `WashingStation`.
   - **Price test:** patches a module-level `core.views.PRICE_SCHEDULE["prices_per_kg"]` dict. Here prices are DB rows, and the response has `prices: [{grade, price_per_kg_rwf}]`.
   - **Risk-check test:** looks for a field named `status`, `state`, `export_status`, `risk_check_status` or `rejection_reason`. This repo returns `is_exportable` and `plot_risk_status_at_delivery`, neither of which is in that set. It also sets `REGISTRY_API_URL`, which this code ignores (always simulator), so the forced failure has no effect.
   - **Docstrings:** they cite `08-kawa-contracts-and-deltas.md` and README text ("static in-code dict… no cache") that are not in this repo.
3. **Summative artifacts are missing.** `docs/autograding/SUMMATIVE_CONTRACT.md` requires them, but there is no `BUG_REPORT.md`, no `DEPLOYMENT.md` and no `summative` tag. The Dockerfile runs `runserver`, its own comment says gunicorn, collectstatic and a non-root user are "Summative work", and `gunicorn` is not in requirements.txt.
4. **Anonymous POSTs are still accepted** on farmers, plots and deliveries, kept for F1 compatibility (`ANONYMOUS_POLICY`). That conflicts with the "require authentication" direction of F2. It is documented in DECISION_LOG.md but is a likely review point. HTTP Basic auth is also enabled.
5. **There is no real registry client**, only the simulator, and `REGISTRY_API_URL` is dead config.
6. **A plot whose risk check never succeeds has no terminal state or reason.** This is the gap staging scenario 3 targets.
7. **Main branch is healthy:** `check` passes, there are no missing migrations, the seed command is idempotent (two runs give the same result), and 302 tests pass.
