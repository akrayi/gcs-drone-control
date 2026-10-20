# Deploying to AKS

[Back to the project](../README.md)

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
