#!/usr/bin/env python3
"""Secrets Resolver — Pluggable Credential Management with Automatic Redaction.

================================================================================
WHY A SECRETS RESOLVER?
================================================================================

Data operations need API keys, database passwords, and tokens.  The naive
approaches all have problems::

    # BAD: Hardcoded
    api_key = "sk-abc123"  # Committed to git, leaked in logs

    # BAD: Environment only
    api_key = os.environ["API_KEY"]  # KeyError in dev, no fallback

    # BAD: Scattered logic
    if env == "prod":
        api_key = vault.get("api_key")
    elif env == "staging":
        api_key = os.environ["API_KEY"]
    else:
        api_key = "test-key"

SecretsResolver provides **layered resolution** with automatic redaction::

    resolver = SecretsResolver([
        EnvSecretBackend(),           # Check env vars first
        FileSecretBackend("/secrets"),  # Then mounted files
        DictSecretBackend(defaults),    # Then defaults
    ])

    api_key = resolver.resolve("EDGAR_API_KEY")
    print(api_key)           # → SecretValue("sk-abc...") — masked in logs
    api_key.get_secret()     # → "sk-abc123" (actual value, use carefully)


================================================================================
ARCHITECTURE: LAYERED RESOLUTION
================================================================================

::

    resolver.resolve("EDGAR_API_KEY")
         │
         ▼
    ┌──────────────────┐    not found     ┌──────────────────┐
    │ EnvSecretBackend │─────────────────►│ FileSecretBackend│
    │                  │                  │                  │
    │ os.environ[      │                  │ /secrets/        │
    │  "EDGAR_API_KEY"]│                  │  EDGAR_API_KEY   │
    └──────────────────┘                  └────────┬─────────┘
                                           not found│
                                                    ▼
                                          ┌──────────────────┐
                                          │ DictSecretBackend│
                                          │                  │
                                          │ {"EDGAR_API_KEY":│
                                          │  "fallback-key"} │
                                          └──────────────────┘

    If no backend has the secret → MissingSecretError


================================================================================
SECURITY: AUTOMATIC REDACTION
================================================================================

SecretValue prevents accidental exposure::

    secret = resolver.resolve("DB_PASSWORD")
    print(secret)         # → SecretValue('****')  — redacted
    str(secret)           # → "****"               — redacted
    repr(secret)          # → "SecretValue('****')"
    f"pw={secret}"        # → "pw=****"
    logger.info(secret)   # → "****" in log output

    secret.get_secret()   # → "actual_password" (explicit access only)

This prevents credentials from appearing in:
    - Log files
    - Error tracebacks
    - Dashboard displays
    - Serialized state


================================================================================
BEST PRACTICES
================================================================================

1. **Never log secrets**::

       logger.info(f"Using key {api_key}")        # BAD — actual value
       logger.info(f"Using key {secret}")          # GOOD — shows "****"
       logger.info(f"Using key {secret.get_secret()}")  # BAD — explicit leak

2. **Use ``resolve_config_secrets()`` for bulk resolution**::

       config = {"db_url": "secret:DB_URL", "api_key": "secret:EDGAR_KEY"}
       resolved = resolve_config_secrets(config, resolver)
       # All "secret:*" values are resolved from backends

3. **Order backends by priority** — Most secure first::

       resolver = SecretsResolver([
           VaultBackend(),         # 1st: HashiCorp Vault (prod)
           EnvSecretBackend(),     # 2nd: Environment variables
           DictSecretBackend({}),  # 3rd: Defaults (dev only)
       ])


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/24_secrets_resolver.py

See Also:
    - :mod:`spine.core.secrets` — SecretsResolver, SecretValue, backends
    - :mod:`spine.core.config` — Configuration that integrates with secrets
"""
import os
import tempfile
from pathlib import Path

from spine.core.secrets import (
    DictSecretBackend,
    EnvSecretBackend,
    FileSecretBackend,
    MissingSecretError,
    SecretValue,
    SecretsResolver,
    resolve_config_secrets,
)


def main():
    print("=" * 60)
    print("Secrets Resolver Examples")
    print("=" * 60)

    # === 1. SecretValue - safe wrapper ===
    print("\n[1] SecretValue - Redacted Output")

    secret = SecretValue("super_secret_password_123")
    print(f"  str(secret):    {secret}")
    print(f"  repr(secret):   {secret!r}")
    print(f"  len(secret):    {len(secret)}")
    print(f"  bool(secret):   {bool(secret)}")
    print(f"  get_secret():   {secret.get_secret()[:4]}****")

    # === 2. Dict backend (testing) ===
    print("\n[2] DictSecretBackend (for testing)")

    backend = DictSecretBackend({
        "api_key": "sk-test-12345",
        "db_password": "pg_pass_67890",
    })
    print(f"  api_key:     {backend.get('api_key')}")
    print(f"  db_password: {backend.get('db_password')}")
    print(f"  missing:     {backend.get('missing')}")
    print(f"  contains('api_key'): {backend.contains('api_key')}")

    # === 3. Environment backend ===
    print("\n[3] EnvSecretBackend (environment variables)")

    os.environ["SPINE_SECRET_API_TOKEN"] = "env_token_abc"
    os.environ["DATABASE_PASSWORD"] = "env_db_pass"

    env_backend = EnvSecretBackend()
    print(f"  API_TOKEN (via SPINE_SECRET_ prefix): {env_backend.get('API_TOKEN')}")
    print(f"  DATABASE_PASSWORD (direct):           {env_backend.get('DATABASE_PASSWORD')}")

    del os.environ["SPINE_SECRET_API_TOKEN"]
    del os.environ["DATABASE_PASSWORD"]

    # === 4. File backend (Docker/K8s secrets) ===
    print("\n[4] FileSecretBackend (file-based secrets)")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create secret files (like Docker secrets)
        (Path(tmpdir) / "api_key").write_text("file_secret_key_xyz")
        (Path(tmpdir) / "db_pass").write_text("  file_db_pass  \n")

        file_backend = FileSecretBackend(secrets_dir=tmpdir)
        print(f"  api_key: {file_backend.get('api_key')}")
        print(f"  db_pass: {file_backend.get('db_pass')} (whitespace stripped)")
        print(f"  missing: {file_backend.get('missing')}")

    # === 5. Multi-backend resolver with priority ===
    print("\n[5] SecretsResolver - Priority Chain")

    resolver = SecretsResolver([
        DictSecretBackend({"api_key": "from_dict", "only_dict": "dict_only"}),
        DictSecretBackend({"api_key": "from_fallback", "only_fallback": "fb_only"}),
    ])
    print(f"  api_key:      {resolver.resolve('api_key')} (first backend wins)")
    print(f"  only_dict:    {resolver.resolve('only_dict')}")
    print(f"  only_fallback:{resolver.resolve('only_fallback')}")

    # === 6. Default values for missing secrets ===
    print("\n[6] Default Values")

    result = resolver.resolve("missing_key", default="fallback_value")
    print(f"  missing_key with default: {result}")

    try:
        resolver.resolve("missing_key")
    except MissingSecretError as e:
        print(f"  missing_key without default: {e}")

    # === 7. SecretValue wrapping ===
    print("\n[7] Resolve as SecretValue (safe for logging)")

    sv = resolver.resolve_secret_value("api_key")
    print(f"  resolve_secret_value('api_key'): {sv}")
    print(f"  Actual value: {sv.get_secret()}")

    # === 8. Config resolution ===
    print("\n[8] resolve_config_secrets (nested config)")

    config = {
        "database": {
            "host": "localhost",
            "port": 5432,
            "password": "secret:api_key",
        },
        "services": {
            "keys": ["secret:only_dict", "plain_value", "secret:only_fallback"],
        },
    }
    resolved = resolve_config_secrets(config, resolver)
    print(f"  host:     {resolved['database']['host']} (unchanged)")
    print(f"  port:     {resolved['database']['port']} (unchanged)")
    print(f"  password: {resolved['database']['password']} (resolved)")
    print(f"  keys:     {resolved['services']['keys']}")

    # === 9. Custom backend ===
    print("\n[9] Custom Backend Implementation")

    class PrefixedBackend(DictSecretBackend):
        """A backend that adds a prefix to keys before lookup."""
        def get(self, name: str) -> str | None:
            return super().get(f"prod_{name}")

    custom = PrefixedBackend({"prod_token": "production_token_123"})
    print(f"  PrefixedBackend.get('token'): {custom.get('token')}")

    print("\n" + "=" * 60)
    print("All secrets resolver examples completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
