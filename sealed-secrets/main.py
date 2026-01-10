import os
import subprocess
import getpass
import bcrypt
import secrets
import base64
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CERT_PATH = os.path.join(SCRIPT_DIR, "sealed-secrets-public.pem")

GREEN = '\033[0;32m'
BLUE = '\033[0;34m'
YELLOW = '\033[1;33m'
NC = '\033[0m'

def print_header(title):
    print(f"{BLUE}================================================================{NC}")
    print(f"{BLUE}              {title}               {NC}")
    print(f"{BLUE}================================================================{NC}")

def print_section(title):
    print(f"\n{YELLOW}----------------------------------------------------------------{NC}")
    print(f"{GREEN}{title}{NC}")

def get_input(prompt, secret=False):
    if secret:
        return getpass.getpass(prompt + ": ")
    return input(prompt + ": ")

def seal_secret(name, namespace, rel_path, data):
    """
    Creates a secret using kubectl and seals it using kubeseal.
    data: dict of key -> value (plain text)
    """
    if not data:
        print("No data provided, skipping update.")
        return

    output_file = os.path.join(REPO_ROOT, rel_path)
    print(f"Sealing secret: {GREEN}{name}{NC} (Namespace: {namespace})")
    print(f"Target file:    {output_file}")

    # Construct kubectl command
    cmd = [
        "kubectl", "create", "secret", "generic", name,
        "-n", namespace,
        "--dry-run=client",
        "-o", "yaml"
    ]
    
    for key, value in data.items():
        cmd.append(f"--from-literal={key}={value}")

    try:
        # Run kubectl to generate secret yaml
        kubectl_process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        secret_yaml, stderr = kubectl_process.communicate()

        if kubectl_process.returncode != 0:
            print(f"Error creating secret: {stderr}")
            return

        # Run kubeseal
        kubeseal_cmd = [
            "kubeseal",
            f"--cert={CERT_PATH}",
            "--controller-name=sealed-secrets-controller",
            "--controller-namespace=kube-system",
            "--format=yaml"
        ]

        with open(output_file, "w") as f:
            kubeseal_process = subprocess.Popen(
                kubeseal_cmd, stdin=subprocess.PIPE, stdout=f, stderr=subprocess.PIPE, text=True
            )
            _, ks_stderr = kubeseal_process.communicate(input=secret_yaml)

            if kubeseal_process.returncode != 0:
                print(f"Error sealing secret: {ks_stderr}")
            else:
                print(f"{GREEN}Successfully updated {output_file}{NC}")

    except FileNotFoundError as e:
        print(f"Error: Required tool not found: {e}")
        print("Ensure kubectl and kubeseal are in your PATH.")

def handle_grafana():
    print_section("1. Grafana Credentials")
    user = get_input("Enter admin-user")
    password = get_input("Enter admin-password", secret=True)
    
    if user and password:
        seal_secret(
            "monitoring-grafana",
            "monitoring",
            "resources/monitoring/sealed-grafana-secret.yaml",
            {"admin-user": user, "admin-password": password}
        )
    else:
        print("Skipping Grafana.")

def handle_renovate():
    print_section("2. Renovate Token")
    print("Requires a GitHub/GitLab Personal Access Token (Scope: repo).")
    token = get_input("Enter token", secret=True)
    
    if token:
        seal_secret(
            "renovate-config",
            "argocd",
            "resources/renovate/sealed-renovate-secret.yaml",
            {"token": token}
        )
    else:
        print("Skipping Renovate.")

def handle_seaweedfs():
    print_section("3. SeaweedFS S3 Credentials")
    admin = get_input("Enter admin username")
    secret = get_input("Enter admin password", secret=True)
    
    if admin and secret:
        seal_secret(
            "seaweedfs-s3-secret",
            "seaweedfs",
            "resources/seaweedfs/sealed-seaweedfs-s3-secret.yaml",
            {"admin": admin, "secret": secret}
        )
    else:
        print("Skipping SeaweedFS.")

def handle_longhorn():
    print_section("4. Longhorn UI Authentication")
    print("Generating htpasswd compatible entry (user:bcrypt_hash).")
    user = get_input("Enter username (e.g., admin)")
    password = get_input("Enter password", secret=True)

    if user and password:
        # Generate bcrypt hash
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode('utf-8')
        htpasswd_entry = f"{user}:{hashed}"
        
        seal_secret(
            "longhorn-auth",
            "longhorn-system",
            "resources/longhorn/sealed-auth-secret.yaml",
            {"users": htpasswd_entry}
        )
    else:
        print("Skipping Longhorn.")

def handle_argocd():
    print_section("5. ArgoCD Secrets")
    password = get_input("Enter admin.password", secret=True)
    
    data = {}
    if password:
        # ArgoCD expects $2a$ or $2y$ usually, but $2b$ (default python bcrypt) is standard now.
        # Python bcrypt uses $2b$. ArgoCD supports it.
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode('utf-8')
        data["admin.password"] = hashed
    
    print("\nServer Secret Key:")
    print("Press Enter to auto-generate a random secure key, or type one manually.")
    key_input = get_input("Enter server.secretkey")
    
    if key_input:
        data["server.secretkey"] = key_input
    else:
        # Generate random base64 key
        rand_bytes = secrets.token_bytes(32)
        data["server.secretkey"] = base64.b64encode(rand_bytes).decode('utf-8')
        print("Auto-generated server.secretkey.")

    if data:
        seal_secret(
            "argocd-secret",
            "argocd",
            "resources/argocd/sealed-argocd-secret.yaml",
            data
        )
    else:
        print("Skipping ArgoCD.")

def main():
    print_header("Sealed Secrets Manager")
    
    if not os.path.exists(CERT_PATH):
        print(f"Error: Public key not found at {CERT_PATH}")
        sys.exit(1)

    handle_grafana()
    handle_renovate()
    handle_seaweedfs()
    handle_longhorn()
    handle_argocd()

    print(f"\n{BLUE}================================================================{NC}")
    print(f"{GREEN}Done!{NC}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(0)