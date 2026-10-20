# Architecture and command safety

[Back to the project](../README.md)

## Project layout

```text
frontend/
  src/App.jsx                 Dashboard, commands, live connection
  src/components/Login.jsx    Sign-in screen
  src/components/FlightMap.jsx Interactive SVG flight area
  src/components/AdminPanel.jsx Account creation and access management
  src/style.css               Responsive mission-control theme
  nginx.conf                  Same-origin API/WebSocket proxy and headers
  Dockerfile                  React build + non-root web server
backend/
  app/main.py                 HTTP endpoints and authenticated WebSocket
  app/security.py             JWT, password hashing, OPA client
  app/domain.py               Command validation and pure safety transitions
  app/service.py              Transactions, row locks, receipts, snapshots
  app/db.py                   SQLAlchemy database models
  app/config.py               Validated runtime settings
  app/manage.py               Explicit schema/bootstrap/revocation commands
  tests/                     Unit and real PostgreSQL/OPA integration tests
  Dockerfile                 Non-root FastAPI image
policy/
  authz.rego                 Separate deny-by-default role policy
  authz_test.rego            Full role/action matrix tests
  Dockerfile                Local OPA image
database/init-app.sh         Creates a non-superuser application DB owner
k8s/                        AKS workloads, identities, networks, TLS examples
gitops/aks/                 Argo CD deployment overlay and pinned image versions
gitops/argocd/              Restricted Argo CD project and application
.github/workflows/         CI tests and automatic v1, v2, v3 releases
scripts/                    Credential generation and Kubernetes secret setup
compose.yaml                Local stack and isolated integration-test services
kustomization.yaml          AKS resource assembly and policy ConfigMaps
.azure/deployment-plan.md   Preparation/validation record
```

## Learn and verify by stage

### 1. Identity and user administration

Passwords are hashed with Argon2. JWTs expire after 15 minutes, require issuer and
audience validation, and use an explicit signing algorithm. Each request checks
the database user's current active status, role, and authentication version.

Admins can create accounts, change roles, disable/enable users, and reset
passwords. Changes revoke that user's existing tokens, including live streams.
An admin cannot disable or demote their own account. Resetting your own password
also signs you out. Five failed password attempts lock an account for five minutes;
this counter is shared in PostgreSQL, not held separately by each API replica.

Verify: create a viewer, sign in as that viewer, and observe the disabled flight
controls. API requests are also denied by OPA, independently of the interface.

### 2. Policy decisions

| Action | Viewer | Pilot | Admin |
|---|---|---|---|
| Read state / live stream | Yes | Yes | Yes |
| Takeoff / move / land / return home | No | Yes | Yes |
| Clear safety lock | No | No | Yes |
| Read and manage user accounts | No | No | Yes |

OPA receives a subject constructed by the backend from verified database data.
The browser cannot provide a trusted role. Unknown actions, missing inputs,
inactive users, and unknown roles are denied. An unreachable or malformed policy
decision fails closed; the backend never substitutes an allow decision.

Verify: `docker compose run --rm policy-tests`. The Rego test checks every role
against every supported action, including both account-management actions.

### 3. Atomic concurrency and safety

Each command has a UUID `request_id`. Normal commands also carry
`expected_version`, the version displayed to the operator. The backend:

1. Authenticates the caller and asks OPA to authorize the action.
2. Opens a PostgreSQL transaction and locks drone row 1 with `SELECT FOR UPDATE`.
3. Checks for a prior receipt with this request ID.
4. Checks the version and applies a valid state transition.
5. Commits the drone update and command receipt together.

Two simultaneous takeoffs from the same version yield one success and one stale
version conflict. Two replicas behave the same as one because the lock is in
PostgreSQL. Repeating the exact same request by the same user returns its original
receipt without reapplying it. Reusing its UUID for another payload/user returns
409. A replayed receipt describes the original outcome; the live dashboard shows
the latest state. Validation/authentication/policy failures happen before command
receipts and are not entries in the flight-command history.

**RETURN_HOME is the explicit safety exception:** it ignores a stale version,
returns an airborne drone to `(0, 0)`, lands it, and sets a persistent safety latch.
If already grounded, it leaves the position unchanged, keeps altitude zero, and
sets the latch. It never takes off to go home.

| Lock order for concurrent requests | Outcome |
|---|---|
| TAKEOFF, then RETURN_HOME | Takeoff commits; return then grounds and latches |
| RETURN_HOME, then TAKEOFF | Return latches; takeoff fails as stale or latched |

After both requests complete successfully or with defined conflicts, the drone
is grounded and latched in either ordering. This is eventual safety arbitration,
not a claim that the first ordering cannot briefly contain an airborne state.
An admin must explicitly clear the latch at the current version before a new
takeoff. A stale clear cannot erase a newer safety command. If infrastructure is
unavailable, a command may not be delivered; clients must check the response and
retry an uncertain result with the same UUID.

MOVE changes the simulator position immediately within a square of ±100 meters.
TAKEOFF sets altitude to 10 meters. LAND preserves position and sets altitude to
zero. The browser's animation is illustrative, not physical flight simulation.

### 4. Live multi-user dashboards

WebSocket connections check Origin and require a token in the first message within
five seconds. Tokens are never placed in URLs. Each connection reads a consistent
shared database snapshot every 500 ms and rechecks authorization. There is no
authoritative in-process drone state and no sticky-session requirement. Reconnects
receive a full snapshot, including the last 20 command receipts.

Verify: move the drone as `pilot1`; observe the same position and version as
`pilot2` and `viewer`. Send RETURN_HOME, then confirm takeoff remains blocked
until an admin clears the lock. Revoke a pilot or change their role and observe
their session close.

Polling snapshots are a deliberate small-lab design. For large fleets or many
connections, use a transactional outbox and a shared broker for fan-out, retain
snapshot recovery, and enforce quotas/backpressure.

## Security boundaries and next steps

This lab implements JWT identity, authorization on every operation, account
revocation, least-privilege workload identities, network isolation, password
hashing, and safe shared-state mutations. It is not a complete production
zero-trust architecture. Internal API-to-OPA and database traffic is not encrypted
by these base manifests. For production, add authenticated service-to-service TLS
or a mesh, database TLS, workload identity/Key Vault integration, an external IdP
with MFA, ingress rate limits, central security/audit logging, backups and restore
tests, image scanning and digest pinning, and a real migration workflow.

Kubernetes Secrets are not encrypted merely because their representation uses
base64. Restrict Secret access and configure appropriate encryption/Key Vault
integration. The database application role is not a superuser, but owns the lab
schema; separate migration and runtime roles for production. HTTP login lockout
limits per-account guessing; it is not a distributed traffic-rate limiter.

Current upstream references: [OPA Rego](https://www.openpolicyagent.org/docs/policy-language),
[AKS network policies](https://learn.microsoft.com/azure/aks/use-network-policies),
[Traefik Kubernetes Ingress](https://doc.traefik.io/traefik/routing/providers/kubernetes-ingress/).
The ingress example avoids depending on the retired community ingress-nginx
controller; see [AKS ingress support timelines](https://learn.microsoft.com/azure/aks/app-routing).
