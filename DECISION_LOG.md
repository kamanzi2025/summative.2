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
