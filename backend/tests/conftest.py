import os

# Test-only signing key; production startup still requires an externally managed secret.
os.environ.setdefault("SECRET_KEY", "sub-egress-test-only-signing-key-not-for-production")
