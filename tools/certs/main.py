import argparse
import base64
import os
import sys

# Configuration: Relative paths from this script to the target resources
RESOURCES = [
    {
        "path": "../../resources/argocd/argocd-cm.yaml",
        "key_marker": "    rootCA: |",
        "indent": "      "
    },
    {
        "path": "../../resources/monitoring/homelab-ca.yaml",
        "key_marker": "  ca-bundle.pem: |",
        "indent": "    "
    }
]

def load_file(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    with open(file_path, 'r') as f:
        return f.read()

def load_binary_file(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    with open(file_path, 'rb') as f:
        return f.read()

def update_yaml_block(file_path, key_marker, indent, new_content):
    """
    Updates a YAML file by looking for a specific key marker (e.g. '  rootCA: |')
    and replacing the following indented block with new_content.
    """
    abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), file_path))
    
    if not os.path.exists(abs_path):
        print(f"[WARN] Resource not found, skipping: {abs_path}")
        return False

    with open(abs_path, 'r') as f:
        lines = f.readlines()

    new_lines = []
    in_block = False
    block_replaced = False
    
    for line in lines:
        # Check if we found the start of the block
        if not block_replaced and line.rstrip() == key_marker.rstrip():
            new_lines.append(line)
            # Insert new content
            for content_line in new_content.strip().split('\n'):
                new_lines.append(f"{indent}{content_line}\n")
            in_block = True
            block_replaced = True
            continue

        if in_block:
            # Check if we are still in the indented block
            # If line is empty, it might be part of the block or separator, 
            # but usually cert blocks don't have empty lines.
            # If line starts with indent, skip it (it's the old content)
            if line.strip() == "":
                # Keep empty lines if they are formatting? 
                # Safer to assume end of block if we hit something less indented or same indent level but different key
                pass 
            elif line.startswith(indent):
                continue
            else:
                # We reached a line that is NOT indented enough, meaning end of block
                in_block = False
                new_lines.append(line)
        else:
            new_lines.append(line)

    with open(abs_path, 'w') as f:
        f.writelines(new_lines)
    
    print(f"[OK] Updated {os.path.basename(abs_path)}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Update CA bundle in GitOps resources")
    parser.add_argument("path", help="Path to the ca-bundle.pem file")
    args = parser.parse_args()

    # Read CA content
    ca_content = load_file(args.path)

    # Validate it looks like a cert
    if "-----BEGIN CERTIFICATE-----" not in ca_content:
        print("Error: The provided file does not look like a PEM certificate bundle.")
        sys.exit(1)

    print(f"Loaded CA bundle from {args.path}")

    # Process resources
    for res in RESOURCES:
        update_yaml_block(
            res["path"],
            res["key_marker"],
            res["indent"],
            ca_content
        )

if __name__ == "__main__":
    main()
