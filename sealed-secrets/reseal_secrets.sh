#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT="$SCRIPT_DIR/sealed-secrets-public.pem"
REPO_ROOT="$SCRIPT_DIR/.."

seal_secret() {
    NAME=$1
    NS=$2
    FILE="$REPO_ROOT/$3"
    KEYS=("${@:4}") # Array of key names

    echo "----------------------------------------------------------------"
    echo "Sealing $NAME in namespace $NS"
    
    ARGS=""
    for KEY in "${KEYS[@]}"; do
        read -p "Enter value for $KEY: " VAL
        if [ -z "$VAL" ]; then
             echo "Skipping empty value for $KEY"
        else
             ARGS="$ARGS --from-literal=$KEY=$VAL"
        fi
    done
    
    if [ -z "$ARGS" ]; then
        echo "No values provided, skipping $FILE"
        return
    fi

    kubectl create secret generic $NAME -n $NS $ARGS --dry-run=client -o yaml | \
    kubeseal --cert "$CERT" --controller-name=sealed-secrets-controller --controller-namespace=kube-system --format=yaml > "$FILE"
    
    echo "Updated $FILE"
}

# Grafana
seal_secret monitoring-grafana monitoring resources/monitoring/sealed-grafana-secret.yaml admin-user admin-password

# Renovate
seal_secret renovate-config argocd resources/renovate/sealed-renovate-secret.yaml token

# SeaweedFS
seal_secret seaweedfs-s3-secret seaweedfs resources/seaweedfs/sealed-seaweedfs-s3-secret.yaml admin secret

# Longhorn
echo "----------------------------------------------------------------"
echo "Sealing longhorn-auth (requires htpasswd content)"
read -p "Enter value for users (htpasswd content like 'user:hashed...'): " LONGHORN_USERS
if [ ! -z "$LONGHORN_USERS" ]; then
    kubectl create secret generic longhorn-auth -n longhorn-system --from-literal=users="$LONGHORN_USERS" --dry-run=client -o yaml | \
    kubeseal --cert "$CERT" --controller-name=sealed-secrets-controller --controller-namespace=kube-system --format=yaml > "$REPO_ROOT/resources/longhorn/sealed-auth-secret.yaml"
    echo "Updated resources/longhorn/sealed-auth-secret.yaml"
fi

# ArgoCD
echo "----------------------------------------------------------------"
echo "Sealing argocd-secret"
echo "Note: admin.password must be a bcrypt hash. server.secretkey is a random string."
read -p "Enter value for admin.password: " ARGO_PWD
read -p "Enter value for server.secretkey: " ARGO_KEY

ARGS=""
if [ ! -z "$ARGO_PWD" ]; then ARGS="$ARGS --from-literal=admin.password=$ARGO_PWD"; fi
if [ ! -z "$ARGO_KEY" ]; then ARGS="$ARGS --from-literal=server.secretkey=$ARGO_KEY"; fi

if [ ! -z "$ARGS" ]; then
    kubectl create secret generic argocd-secret -n argocd $ARGS --dry-run=client -o yaml | \
    kubeseal --cert "$CERT" --controller-name=sealed-secrets-controller --controller-namespace=kube-system --format=yaml > "$REPO_ROOT/resources/argocd/sealed-argocd-secret.yaml"
    echo "Updated resources/argocd/sealed-argocd-secret.yaml"
fi

echo "----------------------------------------------------------------"
echo "Done!"
