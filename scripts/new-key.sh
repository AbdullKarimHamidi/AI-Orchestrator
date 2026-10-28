#!/usr/bin/env sh
# Prints a new Fernet key for ENCRYPTION_KEYS (URL-safe base64 of 32 random bytes).
# To rotate: put the new key FIRST and keep old keys after it, comma-separated.
set -eu
if command -v python3 >/dev/null 2>&1; then
  python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
else
  head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '\n'; echo
fi
