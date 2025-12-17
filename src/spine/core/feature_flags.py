"""Feature flags for runtime capability toggling.

Enables safe rollouts, kill switches, and A/B testing through a simple
registry-based feature flag system with environment override support.

Manifesto:
    Feature flags are essential for production deployments:
    - **Safe rollouts:** Enable features for subset of users/environments
    - **Kill switches:** Disable problematic features without redeployment
    - **Environment-aware:** Different flags for dev/staging/production
    - **Zero dependencies:** No external service required for basic usage

    Spine's approach is deliberately simple:
    - In-memory registry with optional persistence
    - Environment variable overrides (SPINE_FF_<FLAG_NAME>=true/false)
    - Type-safe flag definitions via dataclass
    - Thread-safe operations for concurrent access

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────────┐
        │                    Feature Flag System                          │
        └─────────────────────────────────────────────────────────────────┘

        Registration:
        ┌────────────────────────────────────────────────────────────────┐
        │ FeatureFlags.register("enable_new_parser", default=False)      │
        │ FeatureFlags.register("max_batch_size", default=100, type=int) │
        └────────────────────────────────────────────────────────────────┘
                              │
                              │ stored in
                              ▼
        ┌────────────────────────────────────────────────────────────────┐
        │                    FlagRegistry (thread-safe)                   │
        │  ┌──────────────────────────────────────────────────────────┐  │
        │  │ flags: dict[str, FlagDefinition]                         │  │
        │  │ overrides: dict[str, Any]                                │  │
        │  └──────────────────────────────────────────────────────────┘  │
        └────────────────────────────────────────────────────────────────┘
                              │
                              │ resolved via
                              ▼
        ┌────────────────────────────────────────────────────────────────┐
        │                    Resolution Order                             │
        │  1. Runtime override (FeatureFlags.set())                      │
        │  2. Environment variable (SPINE_FF_<NAME>)                     │
        │  3. Default value from registration                            │
        └────────────────────────────────────────────────────────────────┘

Examples:
    Basic boolean flag:

    >>> from spine.core.feature_flags import FeatureFlags
    >>>
    >>> # Register with default
    >>> FeatureFlags.register("enable_new_parser", default=False)
    >>>
    >>> # Check flag value
    >>> if FeatureFlags.is_enabled("enable_new_parser"):
    ...     use_new_parser()
    ... else:
    ...     use_old_parser()

    Integer/string flag:

    >>> FeatureFlags.register("batch_size", default=100, flag_type=int)
    >>> FeatureFlags.register("log_level", default="INFO", flag_type=str)
    >>>
    >>> batch = FeatureFlags.get("batch_size")  # 100 or env override
    >>> level = FeatureFlags.get("log_level")   # "INFO" or env override

    Runtime override:

    >>> FeatureFlags.set("enable_new_parser", True)
    >>> assert FeatureFlags.is_enabled("enable_new_parser")
    >>>
    >>> FeatureFlags.reset("enable_new_parser")  # back to default

    Context manager for temporary override:

    >>> with FeatureFlags.override("enable_new_parser", True):
    ...     assert FeatureFlags.is_enabled("enable_new_parser")
    >>> # back to default after context

Guardrails:
    - Feature flags should NOT store complex state (use config for that)
    - Flag names must be snake_case (validated on registration)
    - Environment overrides only work for registered flags
    - Don't use feature flags for user-facing personalization (use a proper A/B system)

Performance:
    - Flag lookup: O(1) dict access
    - Environment check: Cached on first access
    - Thread-safe: Uses threading.RLock

Tags:
    feature-flags, feature-toggle, configuration, runtime, spine-core
"""

from __future__ import annotations

import os
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypeVar

T = TypeVar("T")

# Environment variable prefix for flag overrides
ENV_PREFIX = "SPINE_FF_"


class FlagType(str, Enum):
    """Supported flag value types."""

    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STRING = "string"


@dataclass
class FlagDefinition:
    """Definition of a feature flag.

    Attributes:
        name: Flag identifier (snake_case)
        default: Default value when no override present
        flag_type: Type of flag value
        description: Human-readable description
        created_at: When the flag was registered
    """

    name: str
    default: Any
    flag_type: FlagType = FlagType.BOOL
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def parse_env_value(self, env_value: str) -> Any:
        """Parse environment variable string to typed value.

        Args:
            env_value: Raw string from environment variable

        Returns:
            Parsed value in the flag's type
        """
        if self.flag_type == FlagType.BOOL:
            return env_value.lower() in ("true", "1", "yes", "on")
        elif self.flag_type == FlagType.INT:
            return int(env_value)
        elif self.flag_type == FlagType.FLOAT:
            return float(env_value)
        else:  # STRING
            return env_value


class FlagNotFoundError(Exception):
    """Raised when accessing an unregistered flag."""

    def __init__(self, flag_name: str):
        super().__init__(f"Feature flag not registered: {flag_name}")
        self.flag_name = flag_name


class FlagRegistry:
    """Thread-safe registry of feature flags.

    This class manages flag definitions and runtime overrides.
    Use the FeatureFlags static interface instead of this directly.
    """

    def __init__(self):
        self._flags: dict[str, FlagDefinition] = {}
        self._overrides: dict[str, Any] = {}
        self._env_cache: dict[str, Any] = {}
        self._lock = threading.RLock()

    def register(
        self,
        name: str,
        default: Any,
        flag_type: FlagType | None = None,
        description: str = "",
    ) -> FlagDefinition:
        """Register a new feature flag.

        Args:
            name: Flag identifier (must be snake_case)
            default: Default value
            flag_type: Value type (inferred from default if not provided)
            description: Human-readable description

        Returns:
            The registered FlagDefinition

        Raises:
            ValueError: If name is invalid or flag already registered
        """
        # Validate name format
        if not re.match(r"^[a-z][a-z0-9_]*$", name):
            raise ValueError(
                f"Flag name must be snake_case: {name}"
            )

        # Infer type from default if not provided
        if flag_type is None:
            if isinstance(default, bool):
                flag_type = FlagType.BOOL
            elif isinstance(default, int):
                flag_type = FlagType.INT
            elif isinstance(default, float):
                flag_type = FlagType.FLOAT
            else:
                flag_type = FlagType.STRING

        with self._lock:
            if name in self._flags:
                raise ValueError(f"Flag already registered: {name}")

            flag_def = FlagDefinition(
                name=name,
                default=default,
                flag_type=flag_type,
                description=description,
            )
            self._flags[name] = flag_def
            return flag_def

    def get(self, name: str) -> Any:
        """Get the current value of a flag.

        Resolution order:
        1. Runtime override (if set)
        2. Environment variable (SPINE_FF_<NAME>)
        3. Default value

        Args:
            name: Flag identifier

        Returns:
            Current flag value

        Raises:
            FlagNotFoundError: If flag not registered
        """
        with self._lock:
            if name not in self._flags:
                raise FlagNotFoundError(name)

            # Check runtime override first
            if name in self._overrides:
                return self._overrides[name]

            flag_def = self._flags[name]

            # Check environment variable (cached)
            if name not in self._env_cache:
                env_name = f"{ENV_PREFIX}{name.upper()}"
                env_value = os.environ.get(env_name)
                if env_value is not None:
                    try:
                        self._env_cache[name] = flag_def.parse_env_value(env_value)
                    except (ValueError, TypeError):
                        # Invalid env value, fall through to default
                        self._env_cache[name] = None
                else:
                    self._env_cache[name] = None

            if self._env_cache[name] is not None:
                return self._env_cache[name]

            return flag_def.default

    def set(self, name: str, value: Any) -> None:
        """Set a runtime override for a flag.

        Args:
            name: Flag identifier
            value: Override value

        Raises:
            FlagNotFoundError: If flag not registered
        """
        with self._lock:
            if name not in self._flags:
                raise FlagNotFoundError(name)
            self._overrides[name] = value

    def reset(self, name: str) -> None:
        """Remove runtime override for a flag.

        Args:
            name: Flag identifier

        Raises:
            FlagNotFoundError: If flag not registered
        """
        with self._lock:
            if name not in self._flags:
                raise FlagNotFoundError(name)
            self._overrides.pop(name, None)

    def reset_all(self) -> None:
        """Remove all runtime overrides."""
        with self._lock:
            self._overrides.clear()

    def clear_env_cache(self) -> None:
        """Clear the environment variable cache.

        Call this if environment variables change at runtime.
        """
        with self._lock:
            self._env_cache.clear()

    def is_registered(self, name: str) -> bool:
        """Check if a flag is registered."""
        with self._lock:
            return name in self._flags

    def list_flags(self) -> list[FlagDefinition]:
        """List all registered flags."""
        with self._lock:
            return list(self._flags.values())

    def get_definition(self, name: str) -> FlagDefinition | None:
        """Get flag definition if registered."""
        with self._lock:
            return self._flags.get(name)

    def unregister(self, name: str) -> None:
        """Unregister a flag (mainly for testing)."""
        with self._lock:
            self._flags.pop(name, None)
            self._overrides.pop(name, None)
            self._env_cache.pop(name, None)

    def clear(self) -> None:
        """Clear all flags (mainly for testing)."""
        with self._lock:
            self._flags.clear()
            self._overrides.clear()
            self._env_cache.clear()


# Global registry instance
_registry = FlagRegistry()


class FeatureFlags:
    """Static interface for feature flag operations.

    This is the primary API for working with feature flags.
    All methods are thread-safe.
    """

    @staticmethod
    def register(
        name: str,
        default: Any = False,
        flag_type: FlagType | None = None,
        description: str = "",
    ) -> FlagDefinition:
        """Register a new feature flag.

        Args:
            name: Flag identifier (must be snake_case)
            default: Default value (defaults to False for bool flags)
            flag_type: Value type (inferred from default if not provided)
            description: Human-readable description

        Returns:
            The registered FlagDefinition

        Example:
            >>> FeatureFlags.register("enable_cache", default=True)
            >>> FeatureFlags.register("max_workers", default=4, flag_type=FlagType.INT)
        """
        return _registry.register(name, default, flag_type, description)

    @staticmethod
    def get(name: str) -> Any:
        """Get the current value of a flag.

        Args:
            name: Flag identifier

        Returns:
            Current flag value

        Example:
            >>> FeatureFlags.get("max_workers")
            4
        """
        return _registry.get(name)

    @staticmethod
    def is_enabled(name: str) -> bool:
        """Check if a boolean flag is enabled.

        Args:
            name: Flag identifier

        Returns:
            True if flag value is truthy

        Example:
            >>> if FeatureFlags.is_enabled("enable_cache"):
            ...     use_cache()
        """
        return bool(_registry.get(name))

    @staticmethod
    def set(name: str, value: Any) -> None:
        """Set a runtime override for a flag.

        Args:
            name: Flag identifier
            value: Override value

        Example:
            >>> FeatureFlags.set("enable_cache", False)
        """
        _registry.set(name, value)

    @staticmethod
    def reset(name: str) -> None:
        """Remove runtime override for a flag.

        Args:
            name: Flag identifier

        Example:
            >>> FeatureFlags.reset("enable_cache")  # Back to default
        """
        _registry.reset(name)

    @staticmethod
    def reset_all() -> None:
        """Remove all runtime overrides."""
        _registry.reset_all()

    @staticmethod
    @contextmanager
    def override(name: str, value: Any):
        """Temporarily override a flag value.

        Args:
            name: Flag identifier
            value: Temporary override value

        Yields:
            None

        Example:
            >>> with FeatureFlags.override("enable_cache", False):
            ...     assert not FeatureFlags.is_enabled("enable_cache")
            >>> # Original value restored
        """
        with _registry._lock:
            had_override = name in _registry._overrides
            old_value = _registry._overrides.get(name)

        _registry.set(name, value)
        try:
            yield
        finally:
            if had_override:
                _registry.set(name, old_value)
            else:
                _registry.reset(name)

    @staticmethod
    def is_registered(name: str) -> bool:
        """Check if a flag is registered."""
        return _registry.is_registered(name)

    @staticmethod
    def list_flags() -> list[FlagDefinition]:
        """List all registered flags."""
        return _registry.list_flags()

    @staticmethod
    def get_definition(name: str) -> FlagDefinition | None:
        """Get flag definition if registered."""
        return _registry.get_definition(name)

    @staticmethod
    def clear_env_cache() -> None:
        """Clear the environment variable cache."""
        _registry.clear_env_cache()

    @staticmethod
    def _clear_for_testing() -> None:
        """Clear all flags (for testing only)."""
        _registry.clear()

    @staticmethod
    def _unregister_for_testing(name: str) -> None:
        """Unregister a flag (for testing only)."""
        _registry.unregister(name)


# Convenience decorator for feature-gated functions
def feature_flag(
    flag_name: str,
    fallback: Any = None,
    disabled_error: type[Exception] | None = None,
):
    """Decorator to gate a function behind a feature flag.

    Args:
        flag_name: Flag to check
        fallback: Value to return when flag is disabled
        disabled_error: Exception to raise when flag is disabled

    Returns:
        Decorator function

    Example:
        >>> @feature_flag("enable_experimental", fallback="disabled")
        ... def experimental_feature():
        ...     return "enabled"
        >>>
        >>> experimental_feature()  # Returns "disabled" when flag is off
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if FeatureFlags.is_enabled(flag_name):
                return func(*args, **kwargs)
            elif disabled_error is not None:
                raise disabled_error(f"Feature '{flag_name}' is disabled")
            else:
                return fallback
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator
