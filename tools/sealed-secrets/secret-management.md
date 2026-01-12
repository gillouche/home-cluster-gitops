# sealed-secrets

Retrieve public certificate: 

```bash 
kubeseal --controller-name=sealed-secrets-controller --controller-namespace=kube-system --fetch-cert > sealed-secrets-public.pem
```

Create sealed secret:

```bash
kubectl create secret generic my-secret --from-literal=key=value --dry-run=client -o yaml
kubeseal --cert sealed-secrets-public.pem --format yaml > my-sealed-secret.yaml
```
