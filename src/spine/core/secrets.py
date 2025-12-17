"""Secrets resolution for secure credential management.

Provides a pluggable system for resolving secrets from multiple backends:
environment variables, files, Vault, AWS Secrets Manager, etc.

Manifesto:
    Hardcoded secrets are a security anti-pattern:
    - **Source control exposure:** Secrets in code get committed
    - **Environment coupling:** Different credentials per environment
    - **Rotation pain:** Changing secrets requires code changes

    Spine's secrets resolver provides:
    - **Pluggable backends:** Env vars, files, Vault, AWS, etc.
    - **Unified interface:** `resolve_secret(key)` works everywhere
    - **Layered resolution:** Try multiple backends in order
    - **Reference syntax:** `secret:env:DB_PASSWORD` for explicit backend

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────────┐
        │                    Secrets Resolution                           │
        └─────────────────────────────────────────────────────────────────┘

        Configuration Reference:
        ┌────────────────────────────────────────────────────────────────┐
        │ database:                                                       │
        │   password: "secret:env:DB_PASSWORD"     # Environment var     │
        │   api_key: "secret:file:/run/secrets/key" # File-based secret │
        │   token: "secret:vault:db/creds/prod"    # HashiCorp Vault    │
        └────────────────────────────────────────────────────────────────┘
                              │
                              │ resolved by
                              ▼
        ┌────────────────────────────────────────────────────────────────┐
        │                   SecretsResolver                               │
        │  ┌──────────────────────────────────────────────────────────┐  │
        │  │ backends: list[SecretBackend]                            │  │
        │  │   - EnvSecretBackend (SPINE_SECRET_*)                    │  │
        │  │   - FileSecretBackend (/run/secrets/)                    │  │
        │  │   - VaultSecretBackend (optional)                        │  │
        │  │   - AWSSecretBackend (optional)                          │  │
        │  └──────────────────────────────────────────────────────────┘  │
        └────────────────────────────────────────────────────────────────┘
                              │
                              │ returns
                              ▼
        ┌────────────────────────────────────────────────────────────────┐
        │                    Resolved Secret Value                        │
        │  "actual_password_value"                                       │
        └────────────────────────────────────────────────────────────────┘

Examples:
    Basic environment secret:

    >>> from spine.core.secrets import SecretsResolver
    >>>
    >>> resolver = SecretsResolver()
    >>> # Reads from SPINE_SECRET_DB_PASSWORD or DB_PASSWORD env var
    >>> password = resolver.resolve("db_password")

    Using secret references in config:

    >>> config = {
    ...     "database": {
    ...         "password": "secret:env:DB_PASSWORD",
    ...         "api_key": "secret:file:/run/secrets/api_key",
    ...     }
    ... }
    >>> resolved = resolve_config_secrets(config)
    >>> # resolved["database"]["password"] == actual password value

    File-based secrets (Docker/Kubernetes):

    >>> resolver = SecretsResolver(backends=[
    ...     FileSecretBackend(base_path="/run/secrets"),
    ...     EnvSecretBackend(),
    ... ])
    >>> token = resolver.resolve("api_token")  # Reads /run/secrets/api_token

    Custom backend:

    >>> class VaultBackend(SecretBackend):
    ...     def resolve(self, key: str) -> str | None:
    ...         return vault_client.read(f"secret/data/{key}")
    >>>
    >>> resolver = SecretsResolver(backends=[
    ...     VaultBackend(),
    ...     EnvSecretBackend(),  # Fallback
    ... ])

Guardrails:
    - Secrets should NEVER be logged (use SecretValue wrapper)
    - Use environment variables for simple deployments
    - Use file-based secrets for Docker/Kubernetes
    - Vault/AWS for production secrets management
    - Always provide fallback for development environments

Performance:
    - Environment lookup: O(1)
    - File read: Cached after first access
    - Network backends: Consider caching with TTL

Tags:
    secrets, credentials, security, configuration, spine-core
"""

from __future__ import annotations

import os
import re
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MissingSecretError(Exception):
    """Raised when a secret cannot be resolved from any backend."""

    def __init__(self, key: str, tried_backends: list[str] | None = None):
        self.key = key
        self.tried_backends = tried_backends or []

        msg = f"Secret not found: {key}"
        if tried_backends:
            msg += f" (tried: {', '.join(tried_backends)})"
        super().__init__(msg)


class SecretResolutionError(Exception):
    """Raised when a secret reference format is invalid."""

    def __init__(self, message: str):
        super().__init__(message)


# Backward-compat alias
SecretNotFoundError = MissingSecretError

# ---------------------------------------------------------------------------
# SecretValue wrapper
# ---------------------------------------------------------------------------


class SecretValue:
    """Wrapper for secret values that prevents accidental logging.

    The string representation shows ``[REDACTED]`` instead of the value.
    Use ``.get_secret()`` to access the actual value.

    Example:
        >>> secret = SecretValue("my_password")
        >>> print(secret)           # [REDACTED]
        >>> str(secret)             # [REDACTED]
        >>> secret.get_secret()     # "my_password"
    """

    __slots__ = ("_value",)

    def __init__(self, value: str):
        self._value = value

    def get_secret(self) -> str:
        """Get the actual secret value."""
        return self._value

    # Backward compat alias
    get_secret_value = get_secret

    def __str__(self) -> str:
        return "[REDACTED]"

    def __repr__(self) -> str:
        return "SecretValue('[REDACTED]')"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SecretValue):
            return self._value == other._value
        return False

    def __hash__(self) -> int:
        return hash(self._value)

    def __bool__(self) -> bool:
        return bool(self._value)

    def __len__(self) -> int:
        return len(self._value)


# ---------------------------------------------------------------------------
# Secret backends
# ---------------------------------------------------------------------------


class SecretBackend(ABC):
    """Abstract base for secret backends.

    Implement this to add support for new secret sources
    like HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, etc.
    """

    @abstractmethod
    def get(self, name: str) -> str | None:
        """Retrieve a secret by name.

        Args:
            name: Secret identifier

        Returns:
            Secret value or None if not found in this backend
        """
        ...

    def contains(self, name: str) -> bool:
        """Check if this backend has a secret.

        Args:
            name: Secret identifier

        Returns:
            True if the secret exists
        """
        return self.get(name) is not None


class EnvSecretBackend(SecretBackend):
    """Resolve secrets from environment variables.

    Tries multiple naming conventions in order:
    1. ``{KEY}`` (direct name)
    2. ``SPINE_SECRET_{KEY}`` (explicit Spine prefix)
    3. ``{KEY}_SECRET`` (suffixed)
    """

    def get(self, name: str) -> str | None:
        """Resolve secret from environment variables.

        Args:
            name: Secret key

        Returns:
            Secret value or None
        """
        key_upper = name.upper()

        # Try multiple patterns — direct name first for precedence
        patterns = [
            key_upper,                     # Direct name
            f"SPINE_SECRET_{key_upper}",   # Explicit prefix
            f"{key_upper}_SECRET",         # Suffix
        ]

        for pattern in patterns:
            value = os.environ.get(pattern)
            if value is not None:
                return value

        return None


class FileSecretBackend(SecretBackend):
    """Resolve secrets from files.

    Designed for Docker secrets (``/run/secrets/``) and Kubernetes
    mounted secrets. Caches file contents after first read.
    """

    def __init__(self, secrets_dir: str | Path = "/run/secrets"):
        """Initialize file secret backend.

        Args:
            secrets_dir: Directory containing secret files
        """
        self.secrets_dir = Path(secrets_dir)
        self._cache: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> str | None:
        """Resolve secret from file.

        Args:
            name: Secret key (becomes filename)

        Returns:
            File contents (stripped) or None if file doesn't exist
        """
        # Check cache first
        with self._lock:
            if name in self._cache:
                return self._cache[name]

        # Check directory exists
        if not self.secrets_dir.exists():
            return None

        # Try to read file
        secret_path = self.secrets_dir / name
        if not secret_path.exists():
            return None

        try:
            content = secret_path.read_text().strip()
            with self._lock:
                self._cache[name] = content
            return content
        except (OSError, PermissionError):
            return None

    def clear_cache(self) -> None:
        """Clear the file content cache."""
        with self._lock:
            self._cache.clear()


class DictSecretBackend(SecretBackend):
    """In-memory secret backend for testing.

    NOT for production use — stores secrets in plain memory.
    """

    def __init__(self, secrets: dict[str, str] | None = None):
        """Initialize with optional secrets dict.

        Args:
            secrets: Initial secrets mapping
        """
        self._secrets = dict(secrets) if secrets else {}

    def get(self, name: str) -> str | None:
        """Resolve secret from dictionary."""
        return self._secrets.get(name)

    def set(self, key: str, value: str) -> None:
        """Set a secret value (for testing)."""
        self._secrets[key] = value

    def clear(self) -> None:
        """Clear all secrets."""
        self._secrets.clear()


# ---------------------------------------------------------------------------
# Reference patterns
# ---------------------------------------------------------------------------

# Full reference: secret:backend:key  (e.g. secret:env:DB_PASSWORD)
_FULL_REFERENCE_RE = re.compile(r"^secret:(\w+):(.+)$")

# Simple reference: secret:key  (e.g. secret:db_password)
_SIMPLE_REFERENCE_RE = re.compile(r"^secret:(.+)$")

# Sentinel for distinguishing "no default" from None
_SENTINEL = object()


# ---------------------------------------------------------------------------
# SecretsResolver
# ---------------------------------------------------------------------------


class SecretsResolver:
    """Multi-backend secrets resolver.

    Resolves secrets by trying backends in order until one succeeds.

    Args:
        backends: List of backends to try in order.  When constructed
            with a positional list, that list is used directly.
    """

    def __init__(self, backends: list[SecretBackend] | None = None):
        self._backends: list[SecretBackend] = list(backends) if backends is not None else []

    def resolve(self, key: str, default: Any = _SENTINEL) -> str | None:
        """Resolve a secret by key.

        Tries each backend in order until one returns a value.

        Args:
            key: Secret identifier
            default: Value to return if not found (default: raise)

        Returns:
            Secret value

        Raises:
            MissingSecretError: If no backend has the secret and no default given
        """
        tried: list[str] = []
        for backend in self._backends:
            tried.append(type(backend).__name__)
            value = backend.get(key)
            if value is not None:
                return value

        if default is not _SENTINEL:
            return default

        raise MissingSecretError(key, tried)

    def resolve_secret_value(self, key: str) -> SecretValue:
        """Resolve a secret and wrap it in SecretValue for safe handling.

        Args:
            key: Secret identifier

        Returns:
            SecretValue wrapping the resolved secret

        Raises:
            MissingSecretError: If not found
        """
        value = self.resolve(key)
        return SecretValue(value)  # type: ignore[arg-type]

    def resolve_reference(self, reference: str) -> str | None:
        """Resolve a secret reference string.

        Handles references like:
        - ``secret:env:DB_PASSWORD``  — read from environment
        - ``secret:file:/path/to/secret``  — read from file
        - ``secret:backend:key``  — specific registered backend
        - ``plain_key``  — try all backends

        Args:
            reference: Secret reference or plain key

        Returns:
            Resolved secret value

        Raises:
            SecretResolutionError: If reference format is invalid
            MissingSecretError: If secret not found
        """
        full_match = _FULL_REFERENCE_RE.match(reference)
        if full_match:
            backend_name = full_match.group(1)
            key = full_match.group(2)
            return self._resolve_with_backend(backend_name, key)

        # Check if it starts with "secret:" but has no second colon → invalid
        if reference.startswith("secret:"):
            raise SecretResolutionError(
                f"Invalid secret reference format: '{reference}'. "
                "Expected 'secret:<backend>:<key>'."
            )

        # Plain key — try all backends
        return self.resolve(reference)

    def _resolve_with_backend(self, backend_name: str, key: str) -> str | None:
        """Resolve using a specific backend (or built-in handler).

        Built-in backends 'env' and 'file' are always available
        regardless of what backends are registered.

        Args:
            backend_name: Backend identifier
            key: Secret key

        Returns:
            Resolved value

        Raises:
            SecretResolutionError: If backend not known
            MissingSecretError: If secret not found
        """
        # Built-in: env — direct environment lookup
        if backend_name == "env":
            value = os.environ.get(key)
            if value is not None:
                return value
            raise MissingSecretError(key, ["env"])

        # Built-in: file — direct file read
        if backend_name == "file":
            path = Path(key)
            if path.exists():
                try:
                    return path.read_text().strip()
                except (OSError, PermissionError):
                    pass
            raise MissingSecretError(key, ["file"])

        # Registered backends
        for backend in self._backends:
            if getattr(backend, "name", type(backend).__name__) == backend_name:
                value = backend.get(key)
                if value is not None:
                    return value
                raise MissingSecretError(key, [backend_name])

        raise SecretResolutionError(
            f"Invalid secret reference format: unknown backend '{backend_name}'"
        )

    def add_backend(self, backend: SecretBackend, priority: int = -1) -> None:
        """Add a backend to the resolver.

        Args:
            backend: Backend to add
            priority: Position in backend list (-1 = end)
        """
        if priority < 0:
            self._backends.append(backend)
        else:
            self._backends.insert(priority, backend)

    def contains(self, key: str) -> bool:
        """Check if any backend has this secret.

        Args:
            key: Secret identifier

        Returns:
            True if at least one backend has the secret
        """
        return any(backend.get(key) is not None for backend in self._backends)


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


def resolve_config_secrets(
    config: dict[str, Any],
    resolver: SecretsResolver | None = None,
) -> dict[str, Any]:
    """Recursively resolve secret references in a config dict.

    Walks the config tree and replaces any string starting with
    ``secret:`` with the resolved value.

    Patterns handled:
    - ``secret:key``  — resolve *key* from registered backends
    - ``secret:env:KEY``  — resolve via env var
    - ``secret:file:/path``  — resolve via file

    Args:
        config: Configuration dictionary
        resolver: SecretsResolver to use (creates default if None)

    Returns:
        New config dict with secrets resolved

    Example:
        >>> config = {
        ...     "database": {
        ...         "host": "localhost",
        ...         "password": "secret:env:DB_PASSWORD",
        ...     }
        ... }
        >>> resolved = resolve_config_secrets(config)
    """
    if resolver is None:
        resolver = get_resolver()

    def resolve_value(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("secret:"):
            # Try full reference first (secret:backend:key)
            full_match = _FULL_REFERENCE_RE.match(value)
            if full_match:
                return resolver.resolve_reference(value)
            # Simple reference (secret:key) — strip prefix and resolve
            simple_match = _SIMPLE_REFERENCE_RE.match(value)
            if simple_match:
                key = simple_match.group(1)
                return resolver.resolve(key)
        elif isinstance(value, dict):
            return {k: resolve_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [resolve_value(item) for item in value]
        return value

    return resolve_value(config)


# ---------------------------------------------------------------------------
# Global resolver
# ---------------------------------------------------------------------------

_default_resolver: SecretsResolver | None = None


def get_resolver() -> SecretsResolver:
    """Get the global secrets resolver.

    Creates a default resolver with an ``EnvSecretBackend`` if not set.

    Returns:
        SecretsResolver instance
    """
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = SecretsResolver([EnvSecretBackend()])
    return _default_resolver


def set_resolver(resolver: SecretsResolver) -> None:
    """Set the global secrets resolver.

    Args:
        resolver: SecretsResolver to use globally
    """
    global _default_resolver
    _default_resolver = resolver


def resolve_secret(key: str, default: Any = _SENTINEL) -> str | None:
    """Resolve a secret using the global resolver.

    Convenience function for simple secret resolution.

    Args:
        key: Secret key or reference
        default: Fallback value if not found

    Returns:
        Resolved secret value

    Example:
        >>> password = resolve_secret("db_password")
        >>> token = resolve_secret("secret:env:API_TOKEN")
    """
    resolver = get_resolver()
    if default is not _SENTINEL:
        return resolver.resolve(key, default=default)
    return resolver.resolve(key)
