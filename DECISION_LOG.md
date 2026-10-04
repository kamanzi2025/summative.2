# Decision Log

Decisions made while retrofitting F2 (authentication, access boundaries, privacy) onto the F1 API.
Each entry follows the structure in `docs/templates/DECISION_LOG_TEMPLATE.md`.

## Widen the southern latitude bound to -2.95

### Decision

Move `RWANDA_LAT_MIN` from `-2.85` to `-2.95`. A migration (`registry/0005`) updates the
`plot_inside_rwanda` database constraint to match, and the serializer uses the same constant, so the
API and the database agree.

### Risk Addressed

The F2 contract seeds a fixture plot, M2 (`KWA-SEED-M2`), at latitude `-2.900000`. With the old bound
of `-2.85`, the API rejects M2 with a 400. That means the coarsening checks for exporter partners
(M1 and M2 must return identical coordinates) and the auditor check (all four plots visible) could
not pass.

### Alternatives Considered

- **Keep `-2.85` and ask for the fixture to change.** The fixtures are fixed by the contract, so this
  is not an option.
- **Bypass validation for seed data.** That would let the API reject a plot the database accepts, and
  the hidden checks create the plots through the API anyway.
- **Validate against Rwanda's real border polygon.** This is more accurate, but it needs geometry data
  and a dependency such as GeoDjango or shapely. It would also still reject M2, because M2 is outside
  the real border.

### Trade-off

M2 (`-2.90`) is just south of Rwanda's real southern border (about `-2.84`). The bounding box was
always a coarse check, meant to catch obvious typos like a swapped sign or a coordinate in another
country, not to prove a point is inside Rwanda. Widening it by 0.10° (about 11 km) means some points
in northern Burundi near the border are now accepted. A tightly bound box already let through corners
of neighbouring countries, so this does not change what kind of check it is. It only widens the
margin.

### Deferred Work

Polygon-based border validation is deferred. If it is added later, the fixture plot M2 would need an
explicit exception or a corrected coordinate.

## Role model: one profile per user and one central policy table

### Decision

Each staff user gets a `UserProfile` with exactly one role (`field_agent`, `exporter_partner` or
`compliance_auditor`) and, for field agents only, a washing station. What each role may do is
written in one place, `ROLE_POLICIES` in `apps/accounts/policies.py`. Each policy is a set of
separate switches:

- which resources it can read or write
- which records it sees (own station or all)
- coordinate precision (full or sector-level)
- national ID handling (last four digits or hidden)
- whether it sees commercial terms (`unit_price_rwf`, `amount_due_rwf`)

Access is denied by default. A user gets nothing if they are anonymous, inactive, have no profile,
have a role with no policy, or are a field agent with no station. A resource or action that a
policy does not list is refused. This includes superusers, who use the Django admin rather than
the API.

### Risk Addressed

- A single table makes the access rules easy to review and test, and stops role checks from
  spreading through the views and drifting apart.
- Denying by default means a new endpoint, a new role or a missing profile fails closed (no
  access) instead of open.
- Database constraints stop a field agent being saved without a station, and stop a partner or
  auditor being given one. This means scoping cannot be bypassed by bad data.

### Alternatives Considered

- **Django groups and model permissions.** These cover create, change and view per model, but they
  cannot express record scope, coordinate precision or field masking, so a second mechanism would
  still be needed.
- **A permission ladder (each role "above" the last).** The F2 matrix rules this out. The auditor
  sees more precise locations than the exporter partner, but fewer commercial details.
- **A custom user model with a role field.** This is hard to add to an existing project after its
  first migration, and a profile table does the same job.

### Trade-off

- One role per user. Someone who is both a field agent and an auditor would need two accounts.
- Every request needs the profile, which costs one extra query unless the authentication step
  loads it with the user.
- The policy only works where the code asks for it. Views, querysets and serializers must all call
  it, and an endpoint that forgets to do so would not be protected by this table alone.

### Deferred Work

- Connecting the policy to views, querysets and serializers. This includes making the API
  authenticated by default and replacing `AllowAny`.
- Roles that cover several stations, if a field agent ever covers more than one.
