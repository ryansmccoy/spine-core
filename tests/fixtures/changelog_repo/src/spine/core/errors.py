"""Structured error types for spine-core.

Stability: stable
Tier: basic
Since: 0.1.0
Dependencies: stdlib-only
Doc-Types: API_REFERENCE
Tags: errors, exceptions
"""


class SpineError(Exception):
    """Base exception for all spine-core errors."""


class ConfigError(SpineError):
    """Configuration error."""


class ConnectionError(SpineError):
    """Database connection error."""
