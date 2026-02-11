#!/usr/bin/env python3
import base64
import hashlib
import hmac
import json
import os
import time

def b64_encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=')

def generate_jwt(secret_base64, payload):
    header = {"alg": "HS256", "typ": "JWT"}
    secret = base64.b64decode(secret_base64)
    
    parts = [
        b64_encode(json.dumps(header).encode()),
        b64_encode(json.dumps(payload).encode())
    ]
    
    msg = b".".join(parts)
    sig = hmac.new(secret, msg, hashlib.sha256).digest()
    parts.append(b64_encode(sig))
    
    return b".".join(parts).decode()

# 1. Generate HS256 Secret (Base64)
secret_bytes = os.urandom(64)
secret_b64 = base64.b64encode(secret_bytes).decode().strip()

# 2. Generate Bootstrap Token
# We give it all administrative capabilities
payload = {
    "iss": "attic",
    "sub": "bootstrap",
    "iat": int(time.time()),
    # No expiry for the bootstrap token to ensure the job can always run
    "capabilities": ["CreateCache", "ConfigureCache", "Upload", "DeleteCache"]
}

token = generate_jwt(secret_b64, payload)

print("=== Attic Secret Generation ===")
print(f"Server HS256 Secret (server-token-secret):")
print(secret_b64)
print("\nBootstrap JWT Token (bootstrap-token):")
print(token)
print("\n===============================")
print("Copy these into your sealed-attic-secrets.yaml")
