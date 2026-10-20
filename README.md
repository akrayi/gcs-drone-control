# GCS — Zero-Trust Drone Control Simulator

A runnable learning project with one shared simulated drone, multiple operators,
server-side authorization, and database-backed safety arbitration. React provides
the 2D dashboard; FastAPI verifies identity; a separate OPA service evaluates Rego;
PostgreSQL owns the authoritative state. This is a simulator, with no physical
drone integration or flight-controller guarantees.

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

## Run locally with Docker

Install Docker Desktop with Linux containers and Docker Compose v2. From this
project's root, in PowerShell:

```powershell
# Only needed if .env has not already been generated:
./scripts/setup.ps1

docker compose up --build -d
docker compose ps
docker compose logs init
```

On macOS/Linux, use `python3 scripts/setup.py` for the credential-generation step.
The scripts refuse to overwrite an existing `.env`. An initial `.env` has been
generated in the working copy during project preparation; it is ignored by Git.

Open **http://localhost:8080**. Username: **admin**. Read the generated
`BOOTSTRAP_ADMIN_PASSWORD` value in your local `.env` file. There is no shared,
hardcoded password. The initial password is 64 random hexadecimal characters.

Sign in, then use **Operators & access** to create `pilot1`, `pilot2`, and `viewer`
with distinct passwords of at least 12 characters. Open separate browser profiles
or incognito windows to observe synchronized dashboards. Tokens remain only in
browser memory, so reloading requires signing in again.

Useful commands:

```powershell
docker compose logs -f backend opa
docker compose restart backend
docker compose down
```

`down` preserves the database volume. Do not add `-v` unless you intend to erase
all users, passwords, command history, and drone state. Re-running the setup
container does not replace existing accounts or change their passwords.

### What starts

1. PostgreSQL initializes its volume and creates the `gcs` database owner.
2. The `init` container creates tables and bootstraps only the admin account.
3. OPA loads the policy independently of the Python backend.
4. The backend becomes ready after PostgreSQL and the OPA decision endpoint work.
5. The frontend exposes one local port. Database, OPA, and API ports stay private.

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

## Tests

Run the real integration tests against a separate, temporary PostgreSQL database:

```powershell
docker compose --profile test run --build --rm tests
docker compose --profile test run --rm policy-tests
```

The tests service uses `gcs_test`; tests refuse to reset any other database. They
cover simultaneous TAKEOFF/RETURN_HOME, simultaneous takeoffs, duplicate concurrent
requests, grounded safety behavior, stale lock clearing, role denial, user
management, token revocation/expiry, account lockout, and WebSocket synchronization.

For Python-only unit checks with Python 3.12+:

```powershell
python -m venv .venv
./.venv/Scripts/python -m pip install -r backend/requirements.txt
Push-Location backend
../.venv/Scripts/python -m pytest tests/test_domain.py tests/test_security.py -q
Pop-Location
```

For frontend development, use Node 22+, run `npm ci` then `npm run dev` in
`frontend/`, and run the backend on port 8000 with `ALLOWED_ORIGINS` including
`http://localhost:5173`. The Vite proxy forwards `/api` and WebSockets. Production
build: `npm run build`. Formatting is available from the root with `npm run format`.

## Deploy to an existing AKS cluster

These are deployment instructions, not a record of an actual cloud deployment.
Use a dedicated test namespace/cluster and substitute your registry and DNS name.
You need Azure CLI, kubectl, Docker, an ACR registry, AKS credentials, and an
installed ingress controller. Azure CNI powered by Cilium must enforce network
policies. The selected cluster must provide the `managed-csi` storage class.

### 1. Select the target and publish images

```powershell
az account set --subscription YOUR_SUBSCRIPTION_ID
az aks get-credentials --resource-group YOUR_RESOURCE_GROUP --name YOUR_AKS_NAME
kubectl config current-context
kubectl get storageclass managed-csi
kubectl get nodes

az acr login --name YOUR_ACR
docker build -t YOUR_ACR.azurecr.io/gcs-backend:v1 ./backend
docker build -t YOUR_ACR.azurecr.io/gcs-frontend:v1 ./frontend
docker push YOUR_ACR.azurecr.io/gcs-backend:v1
docker push YOUR_ACR.azurecr.io/gcs-frontend:v1
```

AKS's kubelet identity needs pull permission for the ACR. With a conventional
RBAC-enabled registry, configure that using
`az aks update -g YOUR_RESOURCE_GROUP -n YOUR_AKS_NAME --attach-acr YOUR_ACR`.
For ABAC-enabled registries, assign the appropriate repository reader role to the
kubelet identity instead. These commands modify your Azure environment and are
for you to run when the target is confirmed.

For a manual deployment, update `k8s/kustomization.yaml` with your two image names/tags and
`ALLOWED_ORIGINS=https://YOUR_HOSTNAME`. Replace the observer group placeholder in
`k8s/identity.yaml` with the intended Entra group object ID, or remove that example
RoleBinding. It is a namespace observer role without Secret access.

### 2. Create credentials and workloads

Use independently generated credentials for each environment. If you already have
a local `.env`, deliberately prepare a fresh environment-specific file before
using this helper; it reads the root `.env` and does not rotate existing DB users.

```powershell
kubectl apply -f k8s/namespace.yaml
./scripts/create-k8s-secrets.ps1
kubectl kustomize . > rendered.yaml
kubectl apply --dry-run=server -k .
kubectl apply -k .
kubectl -n gcs wait --for=condition=complete job/gcs-bootstrap-v1 --timeout=300s
kubectl -n gcs rollout status statefulset/postgres --timeout=300s
kubectl -n gcs rollout status deployment/backend --timeout=300s
kubectl -n gcs rollout status deployment/frontend --timeout=300s
kubectl -n gcs get pods,svc,pvc
```

The StatefulSet has one PostgreSQL instance and an 8 GiB PVC. Its headless Service
provides stable identity; a separate ClusterIP Service is used by clients.
This is persistence, not database high availability. Do not increase PostgreSQL
replicas to obtain HA; this manifest does not configure replication.

The bootstrap Job alone receives `BOOTSTRAP_ADMIN_PASSWORD` from
`bootstrap-secret`. Long-running API pods receive only the database connection
and JWT signing key from `backend-secret`; the frontend receives no credentials.
PostgreSQL stores Argon2 hashes of user passwords. The bootstrap operation is
idempotent: changing its Secret does not reset an existing admin password.

After confirming you can sign in, the bootstrap Secret can be removed from the
cluster if your operations process no longer needs it. Do not re-run the helper
unintentionally after that, as it recreates the bootstrap Secret. The Job can be
retained as setup history. For subsequent schema changes, introduce versioned
migrations and a new migration Job: `create_all` only initializes schema v1.

### 3. Ingress and TLS

`k8s/ingress.example.yaml` targets **Traefik**, installed separately in namespace
`traefik` with pod label `app.kubernetes.io/name=traefik`. If using another
controller, update the ingress class/annotations and the frontend NetworkPolicy
source selectors together. NetworkPolicies match pod/namespace labels, not
ServiceAccounts. Workload ServiceAccounts have token automount disabled and no
Kubernetes API permission bindings.

Configure your ingress controller's `websecure` listener on 443. Set DNS to its
public IP, replace `gcs.example.com` in the ingress example, and obtain a trusted
certificate for that host. For an existing certificate/key:

```powershell
kubectl -n gcs create secret tls gcs-tls --cert=YOUR_FULLCHAIN_PEM --key=YOUR_PRIVATE_KEY_PEM
kubectl apply -f k8s/ingress.example.yaml
kubectl -n gcs get ingress
```

The example creates an HTTPS-only route. Configure HTTP-to-HTTPS redirection at
the controller if desired. WebSockets use `wss` automatically. A certificate
manager can instead populate `gcs-tls` using your verified DNS/issuer setup.

To test before DNS/TLS is ready, temporarily add `http://localhost:8080` to
`ALLOWED_ORIGINS` in Kustomize, reapply it, and run:

```powershell
kubectl -n gcs port-forward service/frontend 8080:8080
```

Sign in, create two pilots and a viewer, and perform the verification stages above.
Scale the API to confirm shared-state behavior:

```powershell
kubectl -n gcs scale deployment/backend --replicas=3
kubectl -n gcs rollout status deployment/backend
```

### 4. Troubleshooting

| Symptom | Check |
|---|---|
| Admin cannot sign in | Bootstrap Job logs; current DB password may differ from the original bootstrap Secret |
| API not ready | `kubectl -n gcs logs deployment/backend`; OPA policy and database reachability |
| PVC pending | `kubectl -n gcs describe pvc data-postgres-0`; CSI driver, storage class and capacity |
| ImagePullBackOff | Image name/tag and ACR pull permissions |
| UI loads but live connection fails | Exact Origin, TLS, `/api/ws` proxying, ingress policy labels |
| Policy service unavailable | OPA pod, Service endpoints, policy ConfigMap, NetworkPolicy |
| Changed DB secret breaks login | PostgreSQL initialization runs only on an empty volume; rotate the DB role password as well |
| Job immutable error on update | Keep the completed bootstrap Job unchanged; use a new Job name for a new migration |

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

## Automatic CI and Argo CD releases

The repository includes a working pipeline template. It has not been connected
to an Azure account yet. No cloud credentials are stored here. CI runs immediately;
publishing/deployment jobs remain skipped until all four Azure repository variables
are configured.

```text
Feature pull request → CI checks → merge/push to main
  → CI checks again → build gcs-backend:vN + gcs-frontend:vN → push to ACR
  → update deploy branch with version + immutable SHA256 digests
  → Argo CD detects deploy branch → syncs AKS → Kubernetes rolling update
```

`.github/workflows/release.yml` runs only on pushes to `main`. Its workflow run
number generates **v1, v2, v3, ...** automatically. Both application images get the
same version. Failed or superseded queued runs can leave gaps; a re-run keeps the
same number and cannot overwrite an image that already exists. If publishing
partially fails, start a new main-branch run for a new version. If only the GitOps
job fails, re-run that failed job, which can reuse the completed publish outputs.
No `latest` tag is used for application releases. Manifests also pin image digests,
so the deployed content remains fixed even if someone later alters a registry tag.

The **main branch** is the source you edit. The **deploy branch** is generated by
CI and watched by Argo CD. CI merges the tested source into deploy, records the new
image versions/digests, and pushes normally without force-pushing. This retains
release history and prevents loops: deploy-branch pushes do not trigger the
main-branch release workflow. Do not edit deploy directly except for a deliberate
rollback; make configuration changes in main. Rapid pushes are serialized, and
GitHub may coalesce queued runs to the latest source commit.

### One-time connection

1. Use the private `akrayi/gcs-drone-control` repository, with `main` as the release branch.
   Protect main with pull requests and the **Checks / test** status check.
2. Create a GitHub environment named **azure-release**. In Azure, configure a
   federated credential for `repo:YOUR_ORG/YOUR_REPO:environment:azure-release`,
   with audience `api://AzureADTokenExchange`. Give that identity ACR push
   permission scoped to your registry, not cluster-admin access.
3. Add repository variables `ACR_NAME`, `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and
   `AZURE_SUBSCRIPTION_ID`. `ACR_NAME` is the short registry name, without
   `.azurecr.io`. No Azure client secret is needed; the workflow uses OIDC.
   For ABAC-enabled ACR, use the corresponding repository writer role.
4. Allow the repository Actions token to write the generated **deploy** branch.
   Its write permission is limited to the GitOps job. Configure branch rules so
   that automation can update deploy without permitting direct human edits to main.
5. For GitOps mode, keep the placeholder image names in `k8s/kustomization.yaml`:
   CI uses those stable names to replace images in the overlay. Put the real Origin
   in `gitops/aks/kustomization.yaml`. Prepare namespace, external Secrets, ACR
   pull permissions, ingress controller and TLS using the AKS instructions above.
6. Install Argo CD separately. Repository URLs in both files under
   `gitops/argocd/` already point to `akrayi/gcs-drone-control`. Give Argo CD read access using
   its credential mechanism. Wait for the first successful release to create the
   deploy branch, then apply:

```powershell
kubectl apply -f gitops/argocd/project.yaml
kubectl apply -f gitops/argocd/application.yaml
```

The Argo project restricts the application to namespace `gcs` and the listed
resource types. Secrets remain outside Git/Argo. Sync wave 0 creates infrastructure;
wave 1 runs the idempotent bootstrap hook; wave 2 rolls out API/frontend. The hook
is recreated before each sync to avoid immutable Job-image update errors. It skips
an existing admin, so a removed bootstrap Secret does not break later releases.
A fresh database still requires that Secret. The base manifests remain suitable
for manual deployment without Argo.

Auto-sync, pruning, and self-healing are enabled. Namespace and PostgreSQL
StatefulSet carry protection from automatic pruning/deletion; PVCs are retained
by the StatefulSet's default policy. Argo can report a failed sync or unhealthy
rollout; Kubernetes readiness checks keep unready pods out of Service endpoints.
This configuration does **not** automatically roll back a failed release.

### Rollback and upgrades

To roll back application images, make a deliberate commit on deploy restoring the
previous `images` block (version and both digests), then let Argo sync. Keep main
corrected so the next release does not reintroduce the issue. For configuration
regressions, revert the responsible main commit and let CI create a new release.
Database migrations need their own backward-compatible migration plan; reverting
an image does not restore a database backup. Never roll back by deleting the PVC.

The workflow tests real PostgreSQL/OPA, audits Python/JavaScript dependencies,
builds React, and validates both Kustomize variants against Kubernetes schemas.
Published application images pass a Trivy gate for fixable HIGH/CRITICAL findings
before the deploy branch advances. That gate has not been executed locally because
Docker is unavailable. Image signature verification remains a production addition.
External GitHub Actions are pinned to upstream commit SHAs, and Dependabot is
configured to propose dependency/image/action updates. Pinning is not a substitute
for reviewing third-party actions.

References: [GitHub OIDC with Azure](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure),
[Argo CD sync waves](https://argo-cd.readthedocs.io/en/release-3.0/user-guide/sync-waves/).

### AKS managed application routing option

For a new AKS setup, prefer managed Gateway API application routing over the
older managed NGINX variant, whose Azure support ends after November 2026.
The optional `k8s/aks-gateway.example.yaml` uses `approuting-istio` with HTTPS,
an isolated gateway namespace, and an explicit gateway-to-frontend NetworkPolicy.
It is a platform example, excluded from the application Kustomize/Argo project.

With a supported current Azure CLI, enable the feature on your selected cluster:

```powershell
az aks update -g YOUR_RESOURCE_GROUP -n YOUR_AKS_NAME --enable-gateway-api --enable-app-routing-istio
kubectl get gatewayclass approuting-istio
kubectl create namespace gcs-ingress
kubectl -n gcs-ingress create secret tls gcs-tls --cert=YOUR_FULLCHAIN_PEM --key=YOUR_PRIVATE_KEY_PEM
kubectl apply -f k8s/aks-gateway.example.yaml
kubectl -n gcs-ingress get gateway gcs-gateway
```

Replace the sample hostname first, match it in `ALLOWED_ORIGINS`, and point DNS at
the Gateway's address. Choose this or the Traefik example, not both for the same
hostname. Validate managed proxy labels and HTTPS/WebSocket behavior on the target
cluster. Gateway CRDs are not included in the core Kubernetes schema checks.
See [Microsoft's application-routing guide](https://learn.microsoft.com/azure/aks/app-routing-gateway-api).

### Delete and reuse the test environment

Deleting Azure resources does not delete your GitHub repository. You can recreate
ACR and AKS, restore Secrets and ingress/TLS, reconnect identities, install Argo CD,
and run **Version, publish and deploy → Run workflow → main** to build a new vN
release. If registry or identity IDs change, update the GitHub variables and role
assignments. The workflow is also manually runnable from main for this purpose.

Database contents do not survive deleting their storage unless you create and
retain a backup. Deleting ACR removes its images; CI can rebuild them from source.
Deleting AKS removes its cluster configuration, including installed Argo CD and
Secrets. DNS may need a new IP. Before cleanup, decide whether to retain a database
backup. Check the dedicated test resource group, AKS node resource group, and any
external disks, IPs, DNS zones, registries, or monitoring resources for remaining
charges. Stopping AKS saves compute but is not equivalent to deleting all billable
resources. Nothing in this project deletes your Azure resources automatically.
See [AKS deletion behavior](https://learn.microsoft.com/azure/aks/delete-cluster).
