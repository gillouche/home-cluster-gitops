import argparse
import base64
import os
import sys

def transform_ca_bundle(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    with open(file_path, 'rb') as f:
        content = f.read()

    # Encode to base64 and remove newlines
    encoded = base64.b64encode(content).decode('utf-8')

    # Validation: decode it back and compare
    decoded = base64.b64decode(encoded)
    if decoded != content:
        print("Error: Validation failed! Decoded content does not match original.")
        sys.exit(1)



    return encoded, content.decode('utf-8')

def main():
    parser = argparse.ArgumentParser(description="Transform CA bundle file into values for vault-issuer.yaml and argocd-cm.yaml")
    parser.add_argument("path", help="Path to the ca bundle file")
    args = parser.parse_args()

    encoded_string, raw_content = transform_ca_bundle(args.path)
    
    print("--- vault-issuer.yaml (base64 encoded) ---")
    print(encoded_string)
    print("\n")
    
    print("--- argocd-cm.yaml (PEM content) ---")
    print(raw_content)

if __name__ == "__main__":
    main()
