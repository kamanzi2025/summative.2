# RBAC Matrix

The role model of the Kawa Network API, for a human reader. The automated F2 checks do not parse
this file; they call `python manage.py seed_rbac_fixtures` and then use the API (see the
[F2 contract](autograding/F2_CONTRACT.md)). The reasons behind each choice are in
[DECISION_LOG.md](../DECISION_LOG.md).

## Solange's three questions

The F2 brief starts from three questions the F1 system could not answer. Each now has an answer
from the policy and a check against the audit log (`GET /api/audit-log/`, `compliance_auditor`
only):

| Question | Answer from the policy | Evidence from the audit log |
|---|---|---|
| Who can see a plot's exact coordinates? | Field agents, for their own station's plots only, and compliance auditors. Exporter partners never: they get the sector's reference point. | Who actually did: `?resource=plots&coordinate_precision=full` |
| Who has looked at farmer identity data this season? | Field agents see the last 4 digits of the national ID for their station's farmers. No other role receives it in any form. | `?resource=farmers&national_id=last_four&occurred_after=2026-03-01T00:00:00Z` |
| What precision leaves the system when provenance goes to a buyer? | Sector precision: one fixed reference point per sector, identical for every plot in it, never a rounding of the real coordinate. | `?role=exporter_partner&resource=plots`: every row has `coordinate_precision: "sector"` |

`tests/test_audit_log.py::test_solanges_questions_are_one_query_each` runs these three queries.

## The access matrix

| Role | `GET /api/deliveries/` | `GET /api/plots/` | Farmer national ID | Audit log |
|---|---|---|---|---|
| `field_agent` | own washing station only | own station's plots, full coordinates | masked, last 4 digits (`************6789`) | no access (`403`) |
| `exporter_partner` | all stations | all plots, coordinates replaced by the sector's reference point | field not present | no access (`403`) |
| `compliance_auditor` | all stations, metadata only: no `unit_price_rwf` or `amount_due_rwf` | all plots, full coordinates | field not present | read (`GET /api/audit-log/`) |
| unauthenticated | `401` | `401` | n/a | `401` |
| authenticated, no role | all stations, no commercial terms; may create | all plots, sector reference point; may create | not present | no access (`403`) |

### Every endpoint, by role

R = read, W = write (create). A blank cell is `403`. For anonymous callers every protected
endpoint returns `401`.

| Endpoint | `field_agent` | `exporter_partner` | `compliance_auditor` | no role | Scope for `field_agent` |
|---|---|---|---|---|---|
| `/api/farmers/`, `/api/farmers/{id}/` | R W | R | R | R W | farmers with a plot at the agent's station, or whose `home_station` is that station |
| `/api/plots/`, `/api/plots/{id}/` | R W | R | R | R W | plots whose `washing_station` is the agent's station |
| `/api/plots/{id}/risk-checks/` | R | R | R | R | same as the plot |
| `/api/deliveries/`, `/api/deliveries/{id}/` | R W | R | R | R W | deliveries recorded at the agent's station |
| `/api/stations/`, `/api/stations/{id}/` | R | R | R | R | the agent's own station only |
| `/api/stations/{id}/deliveries/` | R | R | R | R | the agent's own station only |
| `/api/audit-log/` | | | R | | n/a |
| `/api/status/`, `/api/price-schedule/` | public | public | public | public | none (no login needed) |
| `/api/auth/staff-login/`, `/api/auth/api-token/` | public | public | public | public | none (any valid user can log in) |

Exporter partners and compliance auditors see every station. Each field agent sees only their own
station. A record outside a field agent's scope is `404`, the same as a record that does not
exist, so the response never confirms that another station's record exists.

### Field names used for scoping and coarsening

The F1 concepts keep their names, so no mapping is needed:

| Concept | Field | Used for |
|---|---|---|
| Administrative unit | `Plot.sector` (sent and returned by name, e.g. `"Kigoma"`) | coordinate coarsening for exporters |
| Washing station | `Plot.washing_station`, `Delivery.washing_station` (by name, e.g. `"Nyaruguru"`) | field agent scope |
| Farmer's own station | `Farmer.home_station` (by name) | field agent scope for farmers with no plot yet |

## How the role model works

A role is a **profile row**, not a field on Django's `User` and not a group:

- `apps.accounts.models.UserProfile` links one `User` to one `Role`. The roles are
  `field_agent`, `exporter_partner` and `compliance_auditor`. A field agent's profile also links
  to their `washing_station`.
- Database constraints keep the data valid: the role must be one of the three, a field agent
  must have a station, and the other two roles must not have one.
- A logged-in user with **no profile** gets `NO_ROLE_POLICY`: the F1 operations (read and create
  farmers, plots, deliveries) under the most restrictive field rules (no national ID, sector
  reference points, no prices) and no audit log. Anonymous users, inactive users and invalid
  profiles are refused everything. See DECISION_LOG.md, "Logged-in users without a role".

What each role may do is written once, in `ROLE_POLICIES` (`apps/accounts/policies.py`). Each
policy is a set of independent settings:

| Setting | `field_agent` | `exporter_partner` | `compliance_auditor` |
|---|---|---|---|
| resources (read / write) | farmers, plots, deliveries: R W; stations: R | farmers, plots, deliveries, stations: R | farmers, plots, deliveries, stations, audit log: R |
| record scope | own station | all | all |
| coordinates | full | sector | full |
| national ID | last four | hidden | hidden |
| commercial terms | yes | yes | no |

The roles are not a ladder. The auditor sees more precise locations than the exporter but less
commercial data, so no role is simply "more access" than another. Everything not listed is
refused (deny by default).

**How `seed_rbac_fixtures` assigns the roles.** The command finds or creates each user by
username, resets the password to `GraderPass123!`, and creates or updates their `UserProfile`:

| Username | Profile role | Profile `washing_station` |
|---|---|---|
| `field_agent_user` | `field_agent` | `Nyaruguru` |
| `exporter_user` | `exporter_partner` | none |
| `auditor_user` | `compliance_auditor` | none |

The command also creates the seed farmer and the four plots and two deliveries from the contract.
Running it again updates existing rows instead of duplicating them.

**Authentication** only establishes who the user is; the profile decides what they may do.
Staff log in with `POST /api/auth/staff-login/` (a Django session cookie). Integrations exchange
credentials for a token with `POST /api/auth/api-token/` and send `Authorization: Token <key>`.
Both methods produce the same `request.user`, so the role rules apply identically.

## Where enforcement, coarsening and masking happen

Each question is answered in exactly one layer:

| Question | Layer | Code |
|---|---|---|
| May this role call this endpoint (read or write)? | DRF permission class | `RolePolicyPermission` (`apps/accounts/permissions.py`), in `DEFAULT_PERMISSION_CLASSES`. A view must name its `policy_resource`, or it is refused for everyone. |
| Which records may this user see? | Queryset | `Model.objects.visible_to(user)` (`apps/accounts/scoping.py`), used by every list, detail route, sub-route and idempotent-replay lookup, and by the related fields of write requests |
| Which fields, and at what precision? | Serializer fields | `NationalIdField`, `CoordinateField`, `CommercialTermField` and `PolicyFieldsMixin` (`apps/accounts/field_rules.py`) |
| Who accessed what? | Middleware | `AuditLogMiddleware` (`apps/audit/middleware.py`) |

**Why the queryset for record scope.** Lists, detail routes, sub-routes such as
`/api/plots/{id}/risk-checks/`, and the replay lookup for a resent create all start from the same
`visible_to(user)` query, so there is no path that skips it. A permission check on single objects
would not cover lists or replay lookups, and returning `403` would confirm the record exists.

**Why serializer fields for masking and coarsening.** The rule travels with the field. It
applies to list, detail, create and replay responses, and to any serializer that nests a plot or
farmer inside another response, because a nested serializer shares its parent's request. A
separate serializer per role would multiply classes, and a forgotten one would leak data. Masking
in the view would miss nested copies.

- **National ID.** `NationalIdField` returns `************6789` (the last four digits). For roles
  whose policy hides it, `PolicyFieldsMixin` removes the field from the response, so the key does
  not appear at all. The masked form is not shown to those roles either.
- **Coordinates.** `CoordinateField` returns the stored value. For a sector-precision policy it
  returns the plot's **sector reference point** instead (`Sector.reference_latitude` and
  `reference_longitude`). This is a fixed point per sector, not a rounding of the plot's own
  coordinate, so every plot in a sector gets the same answer, and that answer reveals nothing about
  where in the sector the plot is. Plot responses include `coordinate_precision` (`full` or
  `sector`) so a client knows which one it has.
- **Commercial terms.** `CommercialTermField` (`unit_price_rwf`, `amount_due_rwf`) is removed for
  roles without commercial terms. Weight, grade, dates and risk status remain.

A serializer used without a request falls back to the most restrictive rules. The OpenAPI schema
documents every field, and each description says which roles receive it.

**A new endpoint needs no masking code of its own.** It reuses these serializers (or the field
classes and the mixin). `test_every_serializer_exposing_a_protected_field_applies_the_policy`
scans every serializer in `apps/` and fails if a national ID, coordinate or price is exposed
without its field class and `PolicyFieldsMixin`.

### Sector reference points

| Sector | `reference_latitude` | `reference_longitude` |
|---|---|---|
| Kigoma | -2.372500 | 29.381700 |
| Mbazi | -2.418600 | 29.259400 |
| Kibeho | -2.294300 | 29.132800 |
| Ngera | -2.227100 | 29.304600 |
| Ruheru | -2.145800 | 30.611800 |
| Runda | -1.447200 | 29.213700 |

A reference point is **a label in coordinate form, not a location**. Each one is deliberately
placed in a different whole-degree cell from its sector's plots on both axes (data migration
`registry/0010`), so **no rounding of a plot coordinate, at any precision from 0 to 6 decimal
places, equals it, or agrees with it when both are rounded.** `tests/test_sector_reference_points.py`
checks this against every fixture coordinate with three rounding methods, and checks that every
sector's point is distinct. The plot's origin is carried by its `sector` field, which exporters
still receive.

An earlier version used approximate sector centres. The F2 grading run's rounding check flagged
them: a centre is not equal to any rounding of a nearby plot, but the two agree once both are
rounded to 0 or 1 decimal places, so the centre gave away the coarse location rounding would. See
DECISION_LOG.md.

What an exporter receives for the four fixture plots:

| Plot | Stored | Served to `exporter_partner` |
|---|---|---|
| K1 (Kigoma) | -2.540000, 29.710000 | -2.372500, 29.381700 |
| K2 (Kigoma) | -2.660000, 29.790000 | -2.372500, 29.381700 |
| M1 (Mbazi) | -2.510000, 29.520000 | -2.418600, 29.259400 |
| M2 (Mbazi) | -2.900000, 29.900000 | -2.418600, 29.259400 |

### How the audit log records coordinate access without storing coordinates

Each request to a protected endpoint writes one append-only `AuditLog` row. The row records:

- the user and role
- the route and status code
- the IDs of the records returned
- the **field rules applied**: `coordinate_precision` (`full` or `sector`), how national IDs were
  served (`last_four` or `hidden`), and whether commercial terms were included

So "who saw plot 3 at full precision?" can be answered from the plot ID and `coordinate_precision`,
without the log holding a coordinate. Rows never contain coordinates, national IDs, prices,
request or response bodies, or query strings. Refused requests (`401`, `403`, `404`) are recorded
too.
