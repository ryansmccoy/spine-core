#!/usr/bin/env python3
"""Hot-Reload Adapter — dynamic config reloading for runtime adapters.

Demonstrates ``HotReloadAdapter`` which wraps any ``RuntimeAdapter`` and
automatically re-creates it when configuration changes.  This eliminates
the need to restart services during development when adapter settings
like image defaults, resource limits, or connection strings evolve.

Demonstrates:
    1. Basic creation with ``initial_config`` and ``adapter_factory``
    2. ``update_config()`` — manual config change and reload
    3. ``force_reload()`` — force adapter re-creation
    4. ``config_source`` — automatic config polling
    5. ``on_reload`` — callback for reload notifications
    6. Config change detection via SHA-256 hashing
    7. Protocol delegation — all RuntimeAdapter calls forwarded

Architecture::

    HotReloadAdapter  (wraps RuntimeAdapter)
    ├── submit()      →  _maybe_check_config()  →  inner.submit()
    ├── status()      →  _maybe_check_config()  →  inner.status()
    ├── cancel()      →  _maybe_check_config()  →  inner.cancel()
    ├── health_check() → enriched with reload_count & config_hash
    └── update_config(new) → if hash differs → _apply_reload()

    Config Change Detection:
    1. SHA-256 hash of JSON-serialized config
    2. Compare on each operation (throttled by check_interval)
    3. If changed → adapter_factory(new_config) replaces inner
    4. Optional on_reload(old_config, new_config) callback

Key Concepts:
    - **Transparent wrapping**: All ``RuntimeAdapter`` calls are forwarded
      to the inner adapter — callers don't know about hot-reload.
    - **Hash-based detection**: Only reloads when config actually changes
      (SHA-256 of canonical JSON).
    - **Throttled checks**: ``check_interval_seconds`` prevents excessive
      config source polling (default: 5s).
    - **Reload hooks**: ``on_reload`` callback for logging, metrics,
      or side effects on config change.

See Also:
    - ``17_state_machine.py``  — execution state management
    - :mod:`spine.execution.runtimes.hot_reload`

Run:
    python examples/02_execution/18_hot_reload_adapter.py

Expected Output:
    Five sections: basic setup, manual reload, config polling,
    change detection, and health introspection.
"""

from __future__ import annotations

from spine.execution.runtimes.hot_reload import HotReloadAdapter


# =============================================================================
# Simulated adapter (stands in for LocalProcess / Docker / K8s)
# =============================================================================

class FakeAdapter:
    """Minimal adapter stub for demonstration purposes.

    In production this would be a ``LocalProcessAdapter``,
    ``DockerAdapter``, or ``KubernetesAdapter``.
    """

    def __init__(self, config: dict) -> None:
        self._config = dict(config)
        self.name = f"fake({config.get('image', '?')})"

    @property
    def capabilities(self):
        """Stub capabilities."""
        from spine.execution.runtimes._types import RuntimeCapabilities
        return RuntimeCapabilities(
            supports_gpu=self._config.get("gpu", False),
        )

    async def submit(self, spec):
        return f"job-{spec.name}"

    async def status(self, ref):
        from spine.execution.runtimes._types import JobStatus
        return JobStatus(state="succeeded", exit_code=0)

    async def cancel(self, ref):
        return True

    async def health_check(self):
        return {"adapter": self.name, "healthy": True}


def make_adapter(config: dict) -> FakeAdapter:
    """Factory function: config → RuntimeAdapter."""
    return FakeAdapter(config)


def main() -> None:
    """Run all HotReloadAdapter demonstrations."""

    # ─────────────────────────────────────────────────────────────────
    print("=" * 72)
    print("SECTION 1: Basic Hot-Reload Setup")
    print("=" * 72)

    initial = {
        "image": "spine-pipeline:v1.0",
        "max_memory_mb": 512,
        "max_cpu": 2,
        "gpu": False,
    }

    hot = HotReloadAdapter(
        initial_config=initial,
        adapter_factory=make_adapter,
    )

    print(f"\nAdapter name:    {hot.name}")
    print(f"Inner adapter:   {hot.inner.name}")
    print(f"Reload count:    {hot.reload_count}")
    print(f"Current config:  {hot.current_config}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 2: Manual Config Update")
    print("=" * 72)

    # Update config — adapter is re-created
    new_config = {
        "image": "spine-pipeline:v2.0",
        "max_memory_mb": 1024,
        "max_cpu": 4,
        "gpu": True,
    }

    changed = hot.update_config(new_config)
    print(f"\nConfig changed:  {changed}")
    print(f"Inner adapter:   {hot.inner.name}")
    print(f"Reload count:    {hot.reload_count}")
    print(f"GPU enabled:     {hot.current_config['gpu']}")
    print(f"Memory (MB):     {hot.current_config['max_memory_mb']}")

    # Same config again — no reload
    changed_again = hot.update_config(new_config)
    print(f"\nSame config:     changed={changed_again}")
    print(f"Reload count:    {hot.reload_count}  (unchanged)")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 3: Force Reload")
    print("=" * 72)

    hot.force_reload()
    print(f"\nAfter force_reload:")
    print(f"  Reload count: {hot.reload_count}")
    print(f"  Inner:        {hot.inner.name}")
    print(f"  (New adapter instance even though config unchanged)")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 4: Automatic Config Polling")
    print("=" * 72)

    # Simulate an external config source that changes
    config_versions = [
        {"image": "spine:v1", "max_memory_mb": 256, "max_cpu": 1, "gpu": False},
        {"image": "spine:v2", "max_memory_mb": 512, "max_cpu": 2, "gpu": False},
        {"image": "spine:v3", "max_memory_mb": 1024, "max_cpu": 4, "gpu": True},
    ]
    call_count = {"n": 0}

    def config_source() -> dict:
        """Simulated external config source (changes each call)."""
        idx = min(call_count["n"], len(config_versions) - 1)
        call_count["n"] += 1
        return config_versions[idx]

    hot_polling = HotReloadAdapter(
        initial_config=config_versions[0],
        adapter_factory=make_adapter,
        config_source=config_source,
        check_interval_seconds=0,  # Check every time (for demo)
    )

    print(f"\nInitial:       {hot_polling.inner.name}")

    # Each operation triggers a config check
    # Trigger a check by accessing capabilities (which calls _maybe_check_config)
    _ = hot_polling.capabilities
    print(f"After check 1: {hot_polling.inner.name}  (reload #{hot_polling.reload_count})")

    _ = hot_polling.capabilities
    print(f"After check 2: {hot_polling.inner.name}  (reload #{hot_polling.reload_count})")

    # Third check returns same config as second
    _ = hot_polling.capabilities
    print(f"After check 3: {hot_polling.inner.name}  (reload #{hot_polling.reload_count}, no change)")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 5: Reload Callback")
    print("=" * 72)

    reload_log: list[dict] = []

    def on_reload(old_config: dict, new_config: dict) -> None:
        """Track config changes for auditing."""
        reload_log.append({
            "old_image": old_config.get("image"),
            "new_image": new_config.get("image"),
        })

    hot_cb = HotReloadAdapter(
        initial_config={"image": "app:v1", "max_cpu": 1, "max_memory_mb": 256, "gpu": False},
        adapter_factory=make_adapter,
        on_reload=on_reload,
    )

    hot_cb.update_config({"image": "app:v2", "max_cpu": 2, "max_memory_mb": 512, "gpu": False})
    hot_cb.update_config({"image": "app:v3", "max_cpu": 4, "max_memory_mb": 1024, "gpu": True})

    print(f"\nReload log ({len(reload_log)} entries):")
    for entry in reload_log:
        print(f"  {entry['old_image']} → {entry['new_image']}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 6: Config Hash Detection")
    print("=" * 72)

    # The hash is SHA-256 of canonical JSON
    hash_demo = HotReloadAdapter._hash_config({"b": 2, "a": 1})
    hash_same = HotReloadAdapter._hash_config({"a": 1, "b": 2})
    hash_diff = HotReloadAdapter._hash_config({"a": 1, "b": 3})

    print(f"\nHash of {{b:2, a:1}}: {hash_demo[:16]}...")
    print(f"Hash of {{a:1, b:2}}: {hash_same[:16]}...")
    print(f"Same regardless of key order: {hash_demo == hash_same}")
    print(f"Different with different values: {hash_demo != hash_diff}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 7: Health Check With Reload Metadata")
    print("=" * 72)

    print("""
Hot-reload adapter enriches health checks with reload metadata:

    health = await hot.health_check()
    # Returns:
    {
        "adapter": "fake(app:v3)",   # from inner adapter
        "healthy": True,              # from inner adapter
        "hot_reload": {
            "reload_count": 2,        # total reloads
            "config_hash": "a1b2c3d4...",
            "adapter_name": "fake(app:v3)"
        }
    }

This enables monitoring dashboards to track configuration drift
and reload frequency in production/staging environments.
""")

    print("=" * 72)
    print("All HotReloadAdapter demonstrations complete!")
    print("=" * 72)


if __name__ == "__main__":
    main()
