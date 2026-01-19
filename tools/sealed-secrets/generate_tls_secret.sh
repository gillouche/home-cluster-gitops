#!/bin/bash
set -e

# Paths
PKI_DIR="$HOME/.local/share/ansible-home-cluster/pki"
CERT_FILE="$PKI_DIR/wildcard.pem"
KEY_FILE="$PKI_DIR/wildcard.key"
TEMPLATE_FILE="$(dirname "$0")/input/wildcard-tls.yaml"
OUTPUT_FILE="$(dirname "$0")/input/wildcard-tls-generated.yaml"

# Verify files exist
if [[ ! -f "$CERT_FILE" ]]; then
    echo "Error: Certificate file not found at $CERT_FILE"
    echo "Run Ansible playbook first to generate it."
    exit 1
fi

if [[ ! -f "$KEY_FILE" ]]; then
    echo "Error: Key file not found at $KEY_FILE"
    exit 1
fi

echo "Generating Secret from:"
echo "  Cert: $CERT_FILE"
echo "  Key:  $KEY_FILE"

# Base64 encode (compatible with macOS and Linux)
if [[ "$OSTYPE" == "darwin"* ]]; then
    B64_CERT=$(base64 -i "$CERT_FILE" | tr -d '\n')
    B64_KEY=$(base64 -i "$KEY_FILE" | tr -d '\n')
else
    B64_CERT=$(base64 -w 0 "$CERT_FILE")
    B64_KEY=$(base64 -w 0 "$KEY_FILE")
fi

# Generate Secret YAML
cat > "$OUTPUT_FILE" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: wildcard-tls
  namespace: kube-system
type: kubernetes.io/tls
data:
  tls.crt: $B64_CERT
  tls.key: $B64_KEY
EOF

echo "Success! Generated input secret at: $OUTPUT_FILE"
echo "  kubeseal --controller-name=sealed-secrets-controller --controller-namespace=kube-system \\
  --format=yaml < $OUTPUT_FILE > ../../resources/tls/wildcard-tls-sealed.yaml"
