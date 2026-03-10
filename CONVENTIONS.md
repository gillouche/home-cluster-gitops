# Repository Conventions

Conventions and patterns established for this home-cluster GitOps repository, managed by ArgoCD.

---

## Repository Structure

```
apps/                          # ArgoCD Application manifests only
  infra/                       # Infrastructure apps, organized by domain
    argocd/                    # ArgoCD self-management (config, ingress)
    chaos/                     # Chaos engineering (chaos-mesh)
    ci/                        # CI/CD (argo-rollouts, arc, sonarqube, runners)
    data-lake/                 # Data processing (spark-operator, trino, polaris)
    database/                  # Databases (cloudnative-pg, postgres-cluster)
    hardware/                  # Device plugins (nvidia, amdgpu)
    management/                # Dashboards and agents (homepage, overwatchd)
    network/                   # Networking (traefik, coredns, ingresses)
    observability/             # Monitoring stack (prometheus, loki, tempo, vpa, etc.)
    performance/               # Autoscaling (keda)
    security/                  # Policies, secrets, auth (gatekeeper, authelia, reflector)
    storage/                   # Storage backends (longhorn, seaweedfs)
  playground/                  # Playground environment apps and infra

resources/                     # Helm values, extra manifests, and raw configs
  <app-name>/                  # One directory per app
    values.yaml                # Helm values (referenced via $values)
    manifests/                 # Extra Kubernetes manifests (optional)
```

**Key rule:** `apps/` contains only ArgoCD `Application` or `ApplicationSet` manifests. All Helm values, extra manifests, PDBs, and raw Kubernetes resources go in `resources/`.

---

## Multi-Source Helm Pattern

Every Helm-based app uses the multi-source pattern with a `$values` ref:

```yaml
spec:
  sources:
    - chart: <chart-name>
      repoURL: <helm-repo-url>
      targetRevision: <version>
      helm:
        valueFiles:
          - $values/resources/<app>/values.yaml
    - repoURL: https://github.com/gillouche/home-cluster-gitops.git
      targetRevision: HEAD
      ref: values
```

If the app also needs extra manifests from the git repo, add a `path` to the second source or include a third source:

```yaml
    - repoURL: https://github.com/gillouche/home-cluster-gitops.git
      targetRevision: HEAD
      ref: values
      path: resources/<app>/manifests
```

---

## Standard Sync Policy

All apps should include:

```yaml
syncPolicy:
  automated:
    prune: true
    selfHeal: true
  managedNamespaceMetadata:
    labels:
      goldilocks.fairwinds.com/enabled: "true"
  syncOptions:
    - CreateNamespace=true
    - ServerSideApply=true
  retry:
    limit: 3
    backoff:
      duration: 10s
      factor: 2
      maxDuration: 3m
```

**Notes:**
- `CreateNamespace=true` — omit only for apps deploying into pre-existing namespaces (`kube-system`, `argocd`).
- `ServerSideApply=true` — used by all Helm-based apps to prevent field ownership conflicts. Exception: loki (causes StatefulSet volumeClaimTemplates drift).
- `managedNamespaceMetadata` with Goldilocks label — added to apps that own their namespace, enabling VPA recommendations.
- Longhorn uses `retry.limit: 5` due to longer reconciliation times.

---

## Notification Annotations

All apps must have Discord notification annotations in `metadata.annotations`:

```yaml
annotations:
  notifications.argoproj.io/subscribe.on-sync-failed.webhook.discord-infra: ""
  notifications.argoproj.io/subscribe.on-health-degraded.webhook.discord-infra: ""
```

- **`discord-infra`** — used by all infrastructure apps.
- **`discord-playground`** — used by playground apps. Also subscribes to `on-deployed`.

---

## Finalizers

All apps must include the resources finalizer to ensure child resources are cleaned up on app deletion:

```yaml
metadata:
  finalizers:
    - argoproj.io/resources-finalizer
```

---

## Sync Wave Ordering

Sync waves control deployment order. Apps are organized into these tiers:

| Wave | Category | Examples |
|------|----------|---------|
| 0 | Prerequisites / raw resources | data-lake resources |
| 1 | Base infrastructure | coredns, traefik, cloudnative-pg, reflector, authelia, vpa, cluster-policies |
| 2 | Operators & databases | postgres-cluster, longhorn, spark-operator, polaris |
| 3 | Data processing | trino, gatekeeper |
| 5 | CI/CD controllers & performance | arc, keda, sonarqube, nvidia-device-plugin, argocd-ingress |
| 6 | CI/CD runners | overwatchd-runner, container-factory-runner, playground-runner |
| 8 | Storage | seaweedfs |
| 9 | Security constraints & ingresses | gatekeeper-constraints, infra-ingresses |
| 10 | Extended CI/CD | argo-rollouts, monitoring-extra-dashboards |
| 11 | Observability stack | monitoring, loki, kube-state-metrics, blackbox-exporter, goldilocks |
| 12 | Distributed tracing | tempo |
| 14 | Management & testing | homepage, overwatchd, overwatchd-test, renovate |
| 25 | Chaos engineering | chaos-mesh (always last) |

**Guidelines:**
- Lower waves = more foundational. CRD-providing operators go early so dependent apps can use those CRDs.
- Runners (wave 6) depend on their controller (arc at wave 5).
- Observability (wave 11-12) depends on storage and networking being ready.
- Chaos-mesh at wave 25 ensures everything else is stable first.

---

## Naming Conventions

- **App names** match the Helm chart name or the logical service name (e.g., `cloudnative-pg`, `argo-rollouts`).
- **Namespaces** match the app or use the upstream convention (e.g., `cnpg-system`, `gatekeeper-system`, `longhorn-system`).
- **Resource directories** match the app name under `resources/`.

---

## ArgoCD Projects

Apps are organized into 10 projects by domain:

| Project | Domain |
|---------|--------|
| `infra-base` | Networking, ArgoCD self-management, hardware, management dashboards |
| `infra-chaos` | Chaos engineering |
| `infra-ci` | CI/CD pipelines and runners |
| `infra-data-lake` | Data processing (Spark, Trino, Polaris) |
| `infra-database` | Database operators and clusters |
| `infra-observability` | Monitoring, logging, tracing |
| `infra-performance` | Autoscaling (KEDA) |
| `infra-security` | Policies, secrets, authentication |
| `infra-storage` | Persistent storage backends |
| `playground-infra` | Playground environment infrastructure |

Additionally, `playground-apps-{env}` projects are dynamically created by the playground ApplicationSet.

---

## When to Use ignoreDifferences

Add `ignoreDifferences` to prevent false drift on fields managed outside of GitOps:

### CRD-managing apps
Apps that install CustomResourceDefinitions should ignore CRD status and deprecated fields:
```yaml
ignoreDifferences:
  - group: apiextensions.k8s.io
    kind: CustomResourceDefinition
    jsonPointers:
      - /status
      - /spec/preserveUnknownFields
```

### Webhook-managing apps
Apps with admission webhooks should ignore CA bundle rotation:
```yaml
  - group: admissionregistration.k8s.io
    kind: MutatingWebhookConfiguration
    jsonPointers:
      - /webhooks/0/clientConfig/caBundle
  - group: admissionregistration.k8s.io
    kind: ValidatingWebhookConfiguration
    jsonPointers:
      - /webhooks/0/clientConfig/caBundle
```

For apps with multiple webhook entries, use jqPathExpressions instead:
```yaml
  - group: admissionregistration.k8s.io
    kind: MutatingWebhookConfiguration
    jqPathExpressions:
      - .webhooks[].clientConfig.caBundle
```

### Generated secrets
Apps that auto-generate TLS certs or secrets should ignore the data field:
```yaml
  - group: ""
    kind: Secret
    name: <secret-name>
    jsonPointers:
      - /data
```

### Current coverage
| App | CRD | Webhook | Secrets | Other |
|-----|-----|---------|---------|-------|
| gatekeeper | yes | yes | — | — |
| cloudnative-pg | yes | yes | — | — |
| keda | yes | yes | — | — |
| chaos-mesh | yes | yes | yes | Deployment/DaemonSet rollme annotations |
| argo-rollouts | yes | — | — | — |
| spark-operator | yes | — | — | — |
| vpa | yes | — | — | — |
| longhorn | yes | — | — | PriorityClass, ServiceAccount, Ingress |

**Intentionally skipped:** monitoring (Prometheus Operator manages CRDs internally), traefik (CRDs pre-installed).
