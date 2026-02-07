#!/usr/bin/env bash
set -euo pipefail

# Get the script directory (to handle relative paths properly)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/../.."

INPUT_DIR="$PROJECT_ROOT/tools/sealed-secrets/input/secrets"
OUTPUT_DIR="$PROJECT_ROOT/resources/secrets"
CERT="$SCRIPT_DIR/sealed-secrets-public.pem"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Check if input directory is empty
if [ -z "$(ls -A "$INPUT_DIR" 2>/dev/null)" ]; then
   echo "No secrets found in $INPUT_DIR"
   exit 0
fi

# Determine kubeseal command
if command -v kubeseal &> /dev/null; then
    KUBESEAL_CMD="kubeseal"
else
    echo "Error: kubeseal not found in PATH"
    exit 1
fi

echo "Using certificate: $CERT"

# Process all YAML files
# Use find to safely handle spaces and avoid loop issues if empty
find "$INPUT_DIR" -maxdepth 1 \( -name "*.yaml" -o -name "*.yml" \) -print0 | while IFS= read -r -d '' FILE; do
    BASENAME=$(basename "$FILE")
    OUT_FILE="$OUTPUT_DIR/sealed-$BASENAME"
    
    echo "Sealing $BASENAME..."
    
    # Check if namespace is missing in input file and warn?
    # Kubeseal uses the namespace from the input file for the encryption scope.
    # If missing, it defaults to 'default' which might be wrong for 'secrets' namespace.
    # We assume key inputs have namespace set to 'secrets'.
    
    $KUBESEAL_CMD \
        --cert "$CERT" \
        --format yaml \
        < "$FILE" > "$OUT_FILE"
        
    echo "   -> Created $OUT_FILE"
done

echo "All secrets sealed successfully."
