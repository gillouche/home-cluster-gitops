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

    return encoded

def main():
    parser = argparse.ArgumentParser(description="Transform CA bundle file into a base64 string for vault-issuer.yaml")
    parser.add_argument("path", help="Path to the ca bundle file")
    args = parser.parse_args()

    encoded_string = transform_ca_bundle(args.path)
    print(encoded_string)

if __name__ == "__main__":
    main()
