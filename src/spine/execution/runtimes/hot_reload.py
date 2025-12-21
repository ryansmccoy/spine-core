"""Hot-Reload Adapter — wraps a runtime adapter with config reload.

Monitors a configuration source (dict, callback, or file path) and
automatically re-initialises the wrapped adapter when changes are
detected.  Designed for development / staging where adapter settings
(image defaults, resource limits, poll intervals) evolve without
restarts.

Architecture::

    HotReloadAdapter  (implements RuntimeAdapter protocol)
        ├── _inner: RuntimeAdapter  (the real adapter)
        ├── _config_source: Callable → dict | str path
        ├── _last_config: dict       (snapshot for change detection)
        └── _on_reload: Callable     (optional reload hook)

    On each submit/status/cancel call the adapter checks whether
    the config has changed since the last check.  If so, it calls
    ``on_reload(new_config)`` and replaces the inner adapter.

Example::

    from spine.execution.runtimes.hot_reload import HotReloadAdapter
    from spine.execution.runtimes.local_process import LocalProcessAdapter

    def make_adapter(cfg):
        return LocalProcessAdapter(
            default_image=cfg.get("image", "spine:latest"),
        )

    hot = HotReloadAdapter(
        initial_config={"image": "spine:v1"},
        adapter_factory=make_adapter,
    )

    # Later, update the config:
    hot.update_config({"image": "spine:v2"})
    # Next operation uses the new adapter automatically

Manifesto:
    In development, restarting the engine to pick up config
    changes wastes time.  HotReload watches for adapter config
    changes and swaps them in-place without downtime.

Tags:
    spine-core, execution, runtimes, hot-reload, development, config-watch

Doc-Types:
    api-reference
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

from spine.execution.runtimes._types import (
    ContainerJobSpec,
    JobStatus,
    RuntimeCapabilities,
)

logger = logging.getLogger(__name__)


class HotReloadAdapter:
    """RuntimeAdapter wrapper with hot-reload capabilities.

    Parameters
    ----------
    initial_config
        Initial configuration dictionary.
    adapter_factory
        Callable ``(config: dict) → RuntimeAdapter`` that creates
        a new adapter from config.
    config_source
        Optional callable ``() → dict`` that returns the latest config.
        If provided, config is polled on each operation.
    on_reload
        Optional callback ``(old_config, new_config) → None`` invoked
        when a reload is triggered.
    check_interval_seconds
        Minimum seconds between config checks (default: 5).
    """

    def __init__(
        self,
        *,
        initial_config: dict[str, Any],
        adapter_factory: Callable[[dict[str, Any]], Any],
        config_source: Callable[[], dict[str, Any]] | None = None,
        on_reload: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
        check_interval_seconds: float = 5.0,
    ) -> None:
        self._adapter_factory = adapter_factory
        self._config_source = config_source
        self._on_reload = on_reload
        self._check_interval = check_interval_seconds

        self._current_config = copy.deepcopy(initial_config)
        self._config_hash = self._hash_config(initial_config)
        self._inner = adapter_factory(initial_config)
        self._last_check: datetime | None = None
        self._reload_count = 0

    # ------------------------------------------------------------------
    # Config management
    # ------------------------------------------------------------------

    @property
    def current_config(self) -> dict[str, Any]:
        """Return a copy of the current configuration."""
        return copy.deepcopy(self._current_config)

    @property
    def reload_count(self) -> int:
        """Number of times the adapter has been reloaded."""
        return self._reload_count

    @property
    def inner(self) -> Any:
        """The currently active inner adapter."""
        return self._inner

    def update_config(self, new_config: dict[str, Any]) -> bool:
        """Manually update the configuration.

        Parameters
        ----------
        new_config
            New configuration dictionary.

        Returns
        -------
        bool
            ``True`` if the config changed and adapter was reloaded.
        """
        new_hash = self._hash_config(new_config)
        if new_hash == self._config_hash:
            return False

        old_config = self._current_config
        self._apply_reload(old_config, new_config, new_hash)
        return True

    def force_reload(self) -> None:
        """Force a reload even if config hasn't changed."""
        self._apply_reload(self._current_config, self._current_config, self._config_hash)

    # ------------------------------------------------------------------
    # RuntimeAdapter protocol delegation
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Adapter name (delegates to inner)."""
        return f"hot_reload({getattr(self._inner, 'name', 'unknown')})"

    @property
    def capabilities(self) -> RuntimeCapabilities:
        """Adapter capabilities (delegates to inner)."""
        self._maybe_check_config()
        return self._inner.capabilities

    async def submit(self, spec: ContainerJobSpec) -> str:
        """Submit a job (delegates to inner after config check)."""
        self._maybe_check_config()
        return await self._inner.submit(spec)

    async def status(self, external_ref: str) -> JobStatus:
        """Check job status (delegates to inner)."""
        self._maybe_check_config()
        return await self._inner.status(external_ref)

    async def cancel(self, external_ref: str) -> bool:
        """Cancel a job (delegates to inner)."""
        self._maybe_check_config()
        return await self._inner.cancel(external_ref)

    async def logs(self, external_ref: str) -> AsyncIterator[str]:
        """Stream job logs (delegates to inner)."""
        self._maybe_check_config()
        return await self._inner.logs(external_ref)

    async def cleanup(self, external_ref: str) -> None:
        """Cleanup job resources (delegates to inner)."""
        self._maybe_check_config()
        return await self._inner.cleanup(external_ref)

    async def health_check(self) -> dict[str, Any]:
        """Health check (delegates to inner with reload info)."""
        self._maybe_check_config()
        inner_health = {}
        if hasattr(self._inner, "health_check"):
            inner_health = await self._inner.health_check()
        return {
            **inner_health,
            "hot_reload": {
                "reload_count": self._reload_count,
                "config_hash": self._config_hash[:12],
                "adapter_name": getattr(self._inner, "name", "unknown"),
            },
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _maybe_check_config(self) -> None:
        """Check config source if enough time has elapsed."""
        if self._config_source is None:
            return

        now = datetime.now(UTC)
        if self._last_check is not None:
            elapsed = (now - self._last_check).total_seconds()
            if elapsed < self._check_interval:
                return

        self._last_check = now
        try:
            new_config = self._config_source()
        except Exception:
            logger.warning("Failed to fetch config from source", exc_info=True)
            return

        new_hash = self._hash_config(new_config)
        if new_hash != self._config_hash:
            self._apply_reload(self._current_config, new_config, new_hash)

    def _apply_reload(
        self,
        old_config: dict[str, Any],
        new_config: dict[str, Any],
        new_hash: str,
    ) -> None:
        """Reload the inner adapter with new config."""
        logger.info(
            "Hot-reloading adapter (reload #%d, hash %s → %s)",
            self._reload_count + 1,
            self._config_hash[:8],
            new_hash[:8],
        )

        if self._on_reload:
            try:
                self._on_reload(old_config, new_config)
            except Exception:
                logger.warning("on_reload callback failed", exc_info=True)

        self._inner = self._adapter_factory(new_config)
        self._current_config = copy.deepcopy(new_config)
        self._config_hash = new_hash
        self._reload_count += 1

    @staticmethod
    def _hash_config(config: dict[str, Any]) -> str:
        """Deterministic hash of a config dict."""
        canonical = json.dumps(config, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()
