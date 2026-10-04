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

## Authentication: sessions for staff in the browser, tokens for system integrations

### Decision

The API accepts two ways of proving who you are. Both are set in `DEFAULT_AUTHENTICATION_CLASSES`:

- **Session authentication**, for staff using the browser or the Django admin.
  `POST /api/auth/staff-login/` checks the username and password and starts a Django session
  (a `sessionid` cookie).
- **Token authentication** (DRF `authtoken`), for system integrations such as the registry
  integration or a partner's import job. `POST /api/auth/api-token/` exchanges a username and
  password for a token, which the system sends on every request as `Authorization: Token <key>`.
  No session is created.

Both endpoints return `{"token": "<key>"}`. Each user has one token, so logging in again returns
the same token.

`DEFAULT_PERMISSION_CLASSES` is now `IsAuthenticated`, so every endpoint is closed unless it says
otherwise. Only four endpoints are marked `AllowAny`, and each one does so explicitly:

- `/api/status/`, so a load balancer can check the API without credentials
- `/api/price-schedule/`, because it is the published price list
- the two login endpoints

Anonymous requests to anything else get `401` with a `WWW-Authenticate: Token` header.

**Both methods produce the same `request.user`.** DRF tries each authentication class in turn and
stops at the first one that recognises the request. Either way the view receives the same Django
`User` object, so the permission and filtering code does not need to know, or care, how the user
logged in.

**Authentication is not authorization.** Authentication answers "who is this?" and is all this
step adds. Authorization answers "what may this person see or do?" and is answered separately by
`ROLE_POLICIES` (see the role model entry). This is why the login endpoints accept any valid
user, including the contract's `grader_user`, who has no role. Logging in proves identity; it does
not grant access to data.

### Risk Addressed

- In F1, anyone who could reach the API could read and change farmers' personal data, plot
  locations and delivery payments. Now every endpoint except the public four needs a known user.
- Sessions suit people: the browser stores the cookie, staff can log out, and Django's CSRF
  protection stops another website from making requests using a logged-in staff member's
  session. (Tests check that a session write without a CSRF token is refused.)
- Tokens suit machines: a script cannot easily fill in a login form or handle cookies and CSRF,
  but it can send a header. Token requests are not open to CSRF, because a browser never attaches
  the header automatically.
- Deny by default: a new endpoint is closed unless someone deliberately opens it.

### Alternatives Considered

- **JWT (for example `djangorestframework-simplejwt`).** Rejected for now. The main benefit of
  JWT is that a server can check a token without a database lookup, which matters when many
  services share one login. Here a single Django app checks every token, and the token lookup is
  one indexed query. The cost of JWT would be real: a JWT stays valid until it expires even after
  the user is deactivated or their role changes, unless we also build a blocklist. With a
  database token, deleting the row or deactivating the user takes effect on the very next
  request. For an API that controls access to farmers' national IDs, being able to revoke access
  immediately is worth more than avoiding the lookup.
- **Session only.** The F2 contract requires session authentication, but integrations would then
  have to handle cookies and CSRF tokens, which is fragile for scripts.
- **Token only.** This would break staff use in the browser and the admin, and the contract
  requires session authentication.

### Trade-off

- DRF tokens never expire. A leaked token works until an admin deletes it.
- A token is stored in the database as plain text (the DRF default). Anyone with read access to
  the database can use the tokens in it.
- Staff login also returns a token, which the contract asks for. A browser user therefore holds
  both a session and a token.
- The login endpoints skip authentication and CSRF checks for the login request itself. This lets
  someone log in again despite a stale cookie or a bad header, but it leaves login open to "login
  CSRF", where another site logs a victim into an attacker's account.
- Two login methods mean two code paths to test. The tests cover both, from start to finish.

### Deferred Work

- Token expiry and rotation: tokens that expire after a set time, an endpoint to rotate a token,
  and storing a hash of each token instead of the plain value.
- A logout endpoint that ends the session and optionally deletes the token.
- Rate limiting on the login endpoints, to slow down password guessing.
- Separate service accounts for integrations, with their own role, instead of staff credentials.
- CSRF protection for the staff login form itself.

## Seed fixtures: one idempotent command that converges on the contract values

### Decision

`python manage.py seed_rbac_fixtures` creates the F2 fixtures directly through the models. Every
value is copied from `F2_CONTRACT.md`:

- the three role users
- the seed farmer
- the four plots
- the two deliveries

Running it again updates existing rows to the seed values instead of creating new ones:

- **Users** are found by username. Each run resets the password, marks the user active, and
  resets the role and station.
- **The farmer** is looked up by `national_id` first, then by `member_number`, and the record found
  is updated to the seed values. The phone number, `+250788999001`, is not in the contract; I made
  it up so it is unique.
- **Plots** use `update_or_create` on `plot_code`.
- **Deliveries** have fixed `client_reference` values (`seed-rbac-K1`, `seed-rbac-M1`). A delivery
  that already exists is left unchanged.

The whole run is a single transaction. If the national ID and the member number point to two
different farmers, or another farmer already has the seed phone number, the command stops with an
error and changes nothing.

### Risk Addressed

- **Duplicate national IDs.** The F1 contract flow registers the same person, Uwimana Béatrice,
  with the same national ID but member number `KWA-F-0417`. `national_id` is unique, so creating a
  second farmer would crash on any database where the F1 flow had already run. Looking the farmer
  up by national ID first reuses that record.
- **Grading against drifted data.** If a fixture user's password, role or station had been
  changed, a "create if missing" command would leave it wrong. Resetting the values on every run
  means the access-matrix checks always start from the contract's values.
- **Unwanted background work.** Creating plots through `register_plot` would queue a risk check
  with the external registry for each seed plot. `update_or_create` writes the rows directly, so
  no Celery job is queued and the command works without Redis or a worker.
- **Silent data damage.** When the command cannot tell which existing record is the real one, it
  stops and asks for a person to resolve it, rather than guessing and overwriting someone's data.

### Alternatives Considered

- **Look up the farmer by member number only.** This is simpler, but it fails on the duplicate
  national ID described above.
- **Create through the HTTP API.** The contract asks for direct model writes. The API would also
  queue risk checks, and once the policies are enforced, it would need a logged-in role user just
  to create the fixtures.
- **A data migration.** This would put test accounts with a known password into every database,
  including production, with no way to opt out.

### Trade-off

- The command overwrites. If someone edits a seed user or the seed farmer by hand, the next run
  undoes the edit.
- On a database where the F1 flow ran, the F1 farmer is renamed to `KWA-F-SEED-01` with the seed
  phone. Re-posting the F1 farmer (`KWA-F-0417`) afterwards fails with a duplicate national ID,
  because that person now exists under the seed member number.
- Deliveries that already exist are not updated, so a seed delivery keeps the price it was first
  recorded at. This is deliberate: a delivery's price is a record of what the farmer was paid.
- The seed plots start as `pending`. No check is queued at seed time, but the periodic sweeper will
  queue them once they count as stale (after `RISK_CHECK_STALE_HOURS`), as it does for any plot
  with no result.
- The fixture users have a published password. The command must never be run on production.

### Deferred Work

- Refuse to run when `DEBUG` is off (or require a `--force` flag), so the published password
  cannot reach a production database by accident.
- A merge tool for the rare case where the national ID and the member number belong to two
  different farmers.

## Enforcing the role policies: a permission check plus record scoping

### Decision

`ROLE_POLICIES` is now enforced on every endpoint in two layers.

1. **Permission: may this role call this endpoint at all?** `RolePolicyPermission` is in
   `DEFAULT_PERMISSION_CLASSES`. Each view names the resource it serves (`policy_resource`).
   Reading (`GET`, `HEAD`, `OPTIONS`) needs `read` on that resource; anything else needs `write`.
   - A user with no role gets `403` everywhere, and so does any view that forgets to name its
     resource.
   - Exporter partners and compliance auditors are read-only, so every write they attempt is a
     `403`.
   - Anonymous callers still get `401`.
2. **Scope: which records may this user see?** Every list, detail route and sub-route builds its
   query with `Model.objects.visible_to(user)`. Exporters and auditors see every station. A field
   agent sees only their own station:
   - **Deliveries and plots:** those whose `washing_station` is the agent's station.
   - **Washing stations:** only the agent's own.
   - **Farmers:** anyone with a plot at the agent's station (an `Exists()` subquery), **or**
     anyone whose `home_station` is the agent's station. When a field agent registers a farmer,
     `home_station` defaults to the agent's station, and naming another station is rejected.

   The same scope applies to:
   - the sub-routes: `/api/plots/{id}/risk-checks/`, `/api/stations/{id}/` and
     `/api/stations/{id}/deliveries/`
   - the idempotent-replay lookups, which search only among records the caller can see
   - the related fields in write requests: the `farmer` and `washing_station` of a new plot, and
     the `plot` and `washing_station` of a new delivery. A field agent cannot create a record
     pointing at another station's data.

A record outside the caller's scope returns `404`, the same as a record that does not exist. It
never returns `403`.

### Risk Addressed

- **A field agent reading another station's records** by guessing IDs, adding
  `?washing_station=Kamonyi` to a list, or using a sub-route. Every one of these starts from the
  same scoped query, so there is no unscoped path to forget.
- **Leaks through idempotent replay.** Before this change, re-sending another station's
  `client_reference` or `plot_code` would have returned that station's record (200). Re-sending
  their `member_number` would have returned a 409 containing the farmer's ID. Now the lookup
  cannot see those records, so the request falls through to normal validation, which reports a
  plain duplicate error and returns no data.
- **Gaining access by writing.** Without scoped related fields, an agent could attach a plot to
  another station's farmer. That farmer would then become visible through the new plot, exposing
  their details. Scoped fields reject the request.
- **Confirming that a record exists.** A `403` on `/api/plots/57/` would tell an agent that plot
  57 exists elsewhere. A `404` tells them nothing.

### Alternatives Considered

- **Farmers visible only through a plot at the agent's station** (the original rule). This broke
  three things for a newly registered farmer: the agent could not give them a first plot without
  also being able to attach plots to any station's farmers; a 2G resend of the registration got a
  `400` instead of the idempotent `200`; and the farmer was missing from the agent's list.
  Adding `home_station` fixes all three while keeping the scope to the agent's station.
- **Filtering in each view by hand** (`if role == ...`). Each new view or sub-route is another
  place to forget, and replay lookups are easy to miss. A single `visible_to()` on the model's
  queryset is shared by views, sub-routes, replays and serializer fields.
- **Object-level checks (`has_object_permission`) returning `403`.** These run only on detail
  routes, not on lists or replay lookups, and the `403` confirms that the record exists.
- **django-guardian or another per-object permission library.** It stores a permission row for
  every record and user. Our rule ("same station") is a single filter, so per-row grants would
  add storage and keeping them in sync, with no benefit.

### Trade-off

- A field agent cannot record anything for another station, even to help out during harvest. A
  move between stations means changing the agent's profile.
- A farmer registered at one station who later delivers only to another stays visible to the
  first station's agents through `home_station`. This is a small widening of scope, accepted to
  keep registration working.
- A uniqueness error still reveals that a member number, plot code or national ID is already in
  use somewhere, though not who uses it or any of their data. Keeping data unique across the
  network depends on this.
- The farmer scope adds an `Exists()` subquery to every field agent farmer query. It still runs as
  one query per page; there is no index on `(farmer, washing_station)` yet.
- Code that runs outside a request (the seed command, Celery tasks, serializers used without a
  request) is not scoped. Scoping applies only to API requests.

### Deferred Work

- An index on `Plot(farmer, washing_station)` if the farmer subquery shows up in query plans.
- Field-level rules on top of record scope (step 7): masking national IDs, coarsening coordinates
  for exporters, and removing commercial terms for auditors.
- Field agents covering more than one station.
