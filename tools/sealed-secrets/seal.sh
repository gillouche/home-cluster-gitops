#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/../.."

INPUT_DIR="$PROJECT_ROOT/tools/sealed-secrets/input/secrets"
OUTPUT_DIR="$PROJECT_ROOT/resources/secrets"
CERT="$SCRIPT_DIR/sealed-secrets-public.pem"

mkdir -p "$OUTPUT_DIR"

if command -v kubeseal &> /dev/null; then
    KUBESEAL_CMD="kubeseal"
else
    echo "Error: kubeseal not found in PATH"
    exit 1
fi

echo "Using certificate: $CERT"

seal_file() {
    local FILE="$1"
    local BASENAME=$(basename "$FILE")
    local OUT_FILE="$OUTPUT_DIR/sealed-$BASENAME"
    
    echo "Sealing $BASENAME..."
    $KUBESEAL_CMD \
        --cert "$CERT" \
        --format yaml \
        < "$FILE" > "$OUT_FILE"
    echo "   -> Created $OUT_FILE"
}

if [ $# -gt 0 ]; then
    for arg in "$@"; do
        if [ -f "$arg" ]; then
            seal_file "$arg"
        elif [ -f "$INPUT_DIR/$arg" ]; then
            seal_file "$INPUT_DIR/$arg"
        elif [ -f "$INPUT_DIR/$arg.yaml" ]; then
            seal_file "$INPUT_DIR/$arg.yaml"
        else
            echo "Error: File not found: $arg"
            exit 1
        fi
    done
else
    if [ -z "$(ls -A "$INPUT_DIR" 2>/dev/null)" ]; then
       echo "No secrets found in $INPUT_DIR"
       exit 0
    fi
    
    find "$INPUT_DIR" -maxdepth 1 \( -name "*.yaml" -o -name "*.yml" \) -print0 | while IFS= read -r -d '' FILE; do
        seal_file "$FILE"
    done
fi

echo "All secrets sealed successfully."
