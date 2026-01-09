#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT="$SCRIPT_DIR/sealed-secrets-public.pem"
REPO_ROOT="$SCRIPT_DIR/.."

# Colors for better readability
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================================${NC}"
echo -e "${BLUE}              Sealed Secrets Re-encryption Helper               ${NC}"
echo -e "${BLUE}================================================================${NC}"
echo "This script regenerates Sealed Secrets after a new install of sealed secrets."
echo "Since the original private key is lost, new values must be provided."
echo ""

# Function to seal
seal_secret() {
    NAME=$1
    NS=$2
    FILE="$REPO_ROOT/$3"
    KEYS=("${@:4}") # Array of key names

    echo -e "${YELLOW}----------------------------------------------------------------${NC}"
    echo -e "Sealing secret: ${GREEN}$NAME${NC} (Namespace: $NS)"
    echo -e "Target file:    $FILE"
    echo ""
    
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
        echo "No values provided, skipping update for $FILE"
        return
    fi

    kubectl create secret generic $NAME -n $NS $ARGS --dry-run=client -o yaml | \
    kubeseal --cert "$CERT" --controller-name=sealed-secrets-controller --controller-namespace=kube-system --format=yaml > "$FILE"
    
    echo -e "${GREEN}Successfully updated $FILE${NC}"
}

# --- Grafana ---
echo -e "${YELLOW}----------------------------------------------------------------${NC}"
echo -e "${GREEN}1. Grafana Credentials${NC}"
echo "   Create the login for your Grafana dashboard."
seal_secret monitoring-grafana monitoring resources/monitoring/sealed-grafana-secret.yaml admin-user admin-password

# --- Renovate ---
echo -e "${YELLOW}----------------------------------------------------------------${NC}"
echo -e "${GREEN}2. Renovate Token${NC}"
echo "   This requires a GitHub/GitLab Personal Access Token."
echo "   Generate one at: https://github.com/settings/tokens (Scopes: repo)"
seal_secret renovate-config argocd resources/renovate/sealed-renovate-secret.yaml token

# --- SeaweedFS ---
echo -e "${YELLOW}----------------------------------------------------------------${NC}"
echo -e "${GREEN}3. SeaweedFS S3 Credentials${NC}"
echo "   Set any username and password for your S3 storage access."
seal_secret seaweedfs-s3-secret seaweedfs resources/seaweedfs/sealed-seaweedfs-s3-secret.yaml admin secret

# --- Longhorn ---
echo -e "${YELLOW}----------------------------------------------------------------${NC}"
echo -e "${GREEN}4. Longhorn UI Authentication${NC}"
echo "   This requires an 'htpasswd' formatted string."
echo "   Format: user:hashed_password"
echo ""
echo "   To generate this, run the following in another terminal:"
echo "   ${BLUE}htpasswd -nb admin <your-password>${NC}"
echo ""
read -p "Enter the full htpasswd output (e.g., admin:\$apr1\$...): " LONGHORN_USERS

if [ ! -z "$LONGHORN_USERS" ]; then
    kubectl create secret generic longhorn-auth -n longhorn-system --from-literal=users="$LONGHORN_USERS" --dry-run=client -o yaml | \
    kubeseal --cert "$CERT" --controller-name=sealed-secrets-controller --controller-namespace=kube-system --format=yaml > "$REPO_ROOT/resources/longhorn/sealed-auth-secret.yaml"
    echo -e "${GREEN}Successfully updated resources/longhorn/sealed-auth-secret.yaml${NC}"
else
    echo "Skipping Longhorn update."
fi

# --- ArgoCD ---
echo -e "${YELLOW}----------------------------------------------------------------${NC}"
echo -e "${GREEN}5. ArgoCD Secrets${NC}"
echo "   a) admin.password: Requires a Bcrypt hash of your password."
echo "      To generate, run: ${BLUE}htpasswd -nB -C 10 admin${NC}"
echo "      (Then copy ONLY the hash part, starting after 'admin:')"
echo ""
echo "   b) server.secretkey: Requires a random secure string."
echo "      To generate, run: ${BLUE}openssl rand -base64 32${NC}"
echo ""

read -p "Enter admin.password (Bcrypt hash, starts with \$2y\$...): " ARGO_PWD
read -p "Enter server.secretkey (Random string): " ARGO_KEY

ARGS=""
if [ ! -z "$ARGO_PWD" ]; then ARGS="$ARGS --from-literal=admin.password=$ARGO_PWD"; fi
if [ ! -z "$ARGO_KEY" ]; then ARGS="$ARGS --from-literal=server.secretkey=$ARGO_KEY"; fi

if [ ! -z "$ARGS" ]; then
    kubectl create secret generic argocd-secret -n argocd $ARGS --dry-run=client -o yaml | \
    kubeseal --cert "$CERT" --controller-name=sealed-secrets-controller --controller-namespace=kube-system --format=yaml > "$REPO_ROOT/resources/argocd/sealed-argocd-secret.yaml"
    echo -e "${GREEN}Successfully updated resources/argocd/sealed-argocd-secret.yaml${NC}"
else
    echo "Skipping ArgoCD update."
fi

echo -e "${BLUE}================================================================${NC}"
echo -e "${GREEN}Done!${NC}"
