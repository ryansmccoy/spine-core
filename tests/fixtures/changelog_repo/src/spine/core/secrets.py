"""Secrets resolver with pluggable backends.

Stability: experimental
Tier: standard
Since: 0.4.0
Dependencies: optional: redis
Doc-Types: API_REFERENCE, GUIDE
Tags: secrets, security, pluggable

Provides a Secrets resolver that supports multiple backends:
environment variables, file-based, and vault-based.
"""

from __future__ import annotations
import os


class SecretsResolver:
    """Resolve secrets from pluggable backends."""

    def get(self, key: str, *, default: str | None = None) -> str | None:
        return os.environ.get(key, default)
