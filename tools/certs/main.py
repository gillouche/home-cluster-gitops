import argparse
import base64
import os
import sys

# Configuration: Relative paths from this script to the target resources
RESOURCES = [
    {
        "path": "../../resources/argocd/argocd-cm.yaml",
        "key": "rootCA",
        "indent": "    ",
        "mode": "block"
    },
    {
        "path": "../../resources/monitoring/homelab-ca.yaml",
        "key": "ca-bundle.pem",
        "indent": "  ",
        "mode": "block"
    }
]

def load_file(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    with open(file_path, 'r') as f:
        return f.read()

def update_yaml_block(file_path, key, indent, new_content):
    """
    Updates a YAML file by looking for a specific key ending with '|' (block literal)
    and replacing the following indented block.
    """
    key_marker = f"{indent}{key}: |"
    
    with open(file_path, 'r') as f:
        lines = f.readlines()

    new_lines = []
    in_block = False
    block_replaced = False
    
    for line in lines:
        if not block_replaced and line.rstrip() == key_marker.rstrip():
            new_lines.append(line)
            # Insert new content with proper indentation
            block_indent = indent + "  " 
            for content_line in new_content.strip().split('\n'):
                new_lines.append(f"{block_indent}{content_line}\n")
            in_block = True
            block_replaced = True
            continue

        if in_block:
            if line.strip() != "" and (not line.startswith(indent + " ") or line.startswith(indent + key + ":")): 
                in_block = False
                new_lines.append(line)
        else:
            new_lines.append(line)

    with open(file_path, 'w') as f:
        f.writelines(new_lines)
    
    return True

def update_yaml_value(file_path, key, indent, new_content):
    """
    Updates a single YAML key value on the same line.
    """
    key_marker = f"{indent}{key}:"
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
        
    new_lines = []
    replaced = False
    
    for line in lines:
        if not replaced and line.startswith(key_marker):
            new_lines.append(f"{key_marker} {new_content}\n")
            replaced = True
        else:
            new_lines.append(line)
            
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
        
    return replaced

def process_resource(res, ca_content, script_dir):
    abs_path = os.path.abspath(os.path.join(script_dir, res["path"]))
    
    if not os.path.exists(abs_path):
        print(f"[WARN] Resource not found, skipping: {abs_path}")
        return

    mode = res.get("mode", "block")
    
    if mode == "block":
        update_yaml_block(abs_path, res["key"], res["indent"], ca_content)
        print(f"[OK] Updated block in {os.path.basename(abs_path)}")
        
    elif mode == "value_base64":
        # Encode content
        encoded = base64.b64encode(ca_content.encode('utf-8')).decode('utf-8')
        update_yaml_value(abs_path, res["key"], res["indent"], encoded)
        print(f"[OK] Updated enc-value in {os.path.basename(abs_path)}")

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
    
    script_dir = os.path.dirname(__file__)

    # Process resources
    for res in RESOURCES:
        process_resource(res, ca_content, script_dir)

if __name__ == "__main__":
    main()
