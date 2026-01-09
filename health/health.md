# Cluster Health & Troubleshooting Guide

This guide contains useful commands for managing the cluster via ArgoCD and investigating common issues using `kubectl`.

## ArgoCD Management

### Application Status & Sync
```bash
# List all applications and their health/sync status
kubectl get applications -n argocd

# Get detailed status of a specific application
kubectl get application <app-name> -n argocd -o yaml

# Manually trigger a sync for an application
argocd app sync <app-name>
# OR via kubectl (if argocd CLI is not available)
kubectl patch application <app-name> -n argocd --type merge -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}'

# Force refresh of root
kubectl patch application root -n argocd --type merge -p '{"metadata": {"annotations": {"argocd.argoproj.io/refresh": "hard"}}}'
```

### Troubleshooting Sync Errors
```bash
# View sync errors in the application status
kubectl get application <app-name> -n argocd -o jsonpath='{.status.conditions}' | jq

# Check ArgoCD Repo Server logs (useful if manifest generation fails)
kubectl logs -n argocd -l app.kubernetes.io/name=argocd-repo-server
```

---

## Cluster Investigation (kubectl)

### Node Health
```bash
# Check node status and roles
kubectl get nodes -o wide

# Check for resource pressure or taints
kubectl describe node <node-name> | grep -E "Taints|Conditions|Capacity|Allocatable"

# Check Kubelet logs on a specific node (via SSH)
journalctl -u k3s-agent -f
```

### Pod & Workload Troubleshooting
```bash
# List all pods that are NOT in Running status
kubectl get pods -A --field-selector status.phase!=Running

# Get logs for a failing pod
kubectl logs <pod-name> -n <namespace> --all-containers --tail=100

# Describe a pod to see events (Scheduling issues, ImagePullBackOff, etc.)
kubectl describe pod <pod-name> -n <namespace>

# Check for pods stuck in Terminating state
kubectl get pods -A | grep Terminating
# Force delete a stuck pod
kubectl delete pod <pod-name> -n <namespace> --force --grace-period=0
```

### Storage & PVCs (Longhorn)
```bash
# Check PVC status
kubectl get pvc -A

# Check for Unbound PVCs
kubectl get pvc -A | grep -v Bound

# Investigate a PVC issue
kubectl describe pvc <pvc-name> -n <namespace>
```

### Events & Global Visibility
```bash
# View recent cluster events (sorted by time)
kubectl get events -A --sort-by='.lastTimestamp'

# Check cluster-wide resource usage (if metrics-server is installed)
kubectl top nodes
kubectl top pods -A
```

---

## Infrastructure Specifics

### Sealed Secrets
```bash
# Verify if a SealedSecret has been unsealed successfully
kubectl describe sealedsecret <secret-name> -n <namespace>

# Check Sealed Secrets controller logs
kubectl logs -n kube-system -l app.kubernetes.io/name=sealed-secrets
```

### Networking & Ingress
```bash
# List all ingresses and their hosts
kubectl get ingress -A

# Check Traefik logs for routing errors
kubectl logs -n kube-system -l app.kubernetes.io/name=traefik
```