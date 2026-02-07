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


def handle_longhorn():
    print_section("4. Longhorn UI Authentication")
    print("Generating htpasswd compatible entry (user:bcrypt_hash).")
    user = get_input("Enter username (e.g., admin)")
    password = get_input("Enter password", secret=True)

    if user and password:
        # Generate bcrypt hash
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode('utf-8')
        htpasswd_entry = f"{user}:{hashed}"
        print(f"{htpasswd_entry}")
    else:
        print("Skipping Longhorn.")


def main():
    print_header("Sealed Secrets Manager")
    
    if not os.path.exists(CERT_PATH):
        print(f"Error: Public key not found at {CERT_PATH}")
        sys.exit(1)

    handle_longhorn()

    print(f"\n{BLUE}================================================================{NC}")
    print(f"{GREEN}Done!{NC}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(0)