# GCS deployment plan

Status: Ready for Validation. Local preparation is complete; target-cloud validation remains pending.

## Scope
New simulator project in an empty workspace. React/Vite frontend, FastAPI API,
separate OPA service, PostgreSQL persistence. Docker Compose locally; Kubernetes
manifests for an existing AKS cluster. No cloud resources will be provisioned.
Subscription, region, registry, DNS, and TLS certificate are operator inputs at deployment.

## Stages
1. JWT login, database users and OPA role policy.
2. PostgreSQL row locking, idempotent commands, version checks and sticky safety latch.
3. React 2D simulator and authenticated WebSocket snapshots across replicas.
4. Containers, StatefulSet/PVC, Services, workload identities, RBAC, network isolation and TLS examples.
5. Unit, OPA and PostgreSQL integration tests; staged learning and deployment instructions.
6. Admin-managed accounts, generated bootstrap credentials, automatic vN GitHub Actions releases and Argo CD deployment branch.

## Decisions
- Simulator only, one shared drone, immediate deterministic command transitions.
- RETURN_HOME sets a latch even on the ground; only an admin can clear it using the current version.
- Commands lock one database row; state and audit record commit atomically.
- Browser tokens stay in memory; WebSocket authenticates in its first message.
- Separate policy decision service fails closed. DB user role is authoritative.
- Stateless API replicas read shared snapshots; no in-process authoritative state.
- Kubernetes API access is unnecessary for workloads; service account tokens disabled.
- Native Kubernetes YAML/Kustomize for an existing AKS cluster, no AZD template.
- Azure CNI/Cilium policy enforcement and a separately installed ingress controller required.

## 7. Validation proof
- Real PostgreSQL 17.5 + OPA 1.4.2: 26 Python tests passed, including simultaneous commands, atomic rollback, account lifecycle and WebSocket revocation.
- `opa test policy -v`: 4 policy tests passed (full role/action matrix).
- React production build passed. Browser checks in headless Edge passed: admin account creation, two-user synchronization, safety override, viewer restrictions, mobile layout; no JavaScript errors.
- npm and installed Python dependency audits: no known vulnerabilities reported at verification time.
- Docker Compose v2.39.4 `config --quiet`: passed. Docker image builds/runtime and image scanning have not run locally; no Docker engine is installed.
- Kustomize rendered both base and GitOps overlay. Strict Kubernetes 1.34 schema validation passed for 52 rendered resources.
- GitOps image updater tested with v12 and independent SHA256 digests; both Deployment image references match exactly.
- GitHub Actions workflow syntax checked with actionlint; passed. Azure OIDC, registry publication and Argo reconciliation require real accounts/cluster and have not run.
- Manual ingress/Gateway examples require target controller, hostname and certificate. Gateway CRDs need server validation on the selected cluster.

## Remaining deployment inputs
GitHub repository name/owner; subscription, location, registry and cluster; OIDC identity;
DNS/TLS; network policy engine verification; server-side dry run and rollout smoke tests.
No Azure resources or GitHub repositories have been created and no cloud deployment has occurred.
