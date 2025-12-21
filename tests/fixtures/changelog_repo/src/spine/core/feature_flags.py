"""Thread-safe feature flag registry.

Stability: experimental
Tier: basic
Since: 0.4.0
Dependencies: stdlib-only
Doc-Types: API_REFERENCE, TECHNICAL_DESIGN
Tags: feature_flags, registry, thread_safe

Provides a simple but thread-safe feature flag system.

```mermaid
classDiagram
    class FeatureFlagRegistry {
        +register(name, default)
        +is_enabled(name) bool
        +set_override(name, value)
        +clear_overrides()
    }
```
"""

import threading
from typing import Any


class FeatureFlagRegistry:
    """Thread-safe feature flag registry."""

    def __init__(self) -> None:
        self._flags: dict[str, bool] = {}
        self._lock = threading.Lock()

    def register(self, name: str, *, default: bool = False) -> None:
        with self._lock:
            self._flags.setdefault(name, default)

    def is_enabled(self, name: str) -> bool:
        with self._lock:
            return self._flags.get(name, False)
