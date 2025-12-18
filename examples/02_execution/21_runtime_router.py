#!/usr/bin/env python3
"""RuntimeAdapterRouter — multi-runtime registry, routing, and health.

================================================================================
WHY RuntimeAdapterRouter?
================================================================================

Production systems need multiple runtimes — local dev, Docker, Kubernetes,
AWS Batch.  ``RuntimeAdapterRouter`` provides:

- Named adapter registry (register/unregister)
- Automatic default selection (first registered wins)
- Spec-based routing via ``spec.runtime`` field
- Aggregate health checks (``health_all()``)

::

    ┌─────────────────────────────────────────┐
    │           RuntimeAdapterRouter           │
    ├──────────┬───────────┬──────────────────┤
    │  "local" │  "stub"   │  "docker" (TBD)  │
    │ ★ default│           │                  │
    └──────────┴───────────┴──────────────────┘

    spec.runtime = None    → route to default ("local")
    spec.runtime = "stub"  → route to stub adapter


================================================================================
WHAT THIS EXAMPLE DEMONSTRATES
================================================================================

::

    1  Register multiple adapters
    2  Default selection — first registered wins
    3  Override default — set_default()
    4  Spec-based routing — spec.runtime pins adapter
    5  Unregister an adapter
    6  Aggregate health checks — health_all()
    7  Unknown runtime error handling


================================================================================
RUN IT
================================================================================

::

    python examples/02_execution/21_runtime_router.py

See Also:
    - ``19_local_process_adapter.py`` — LocalProcessAdapter details
    - ``20_job_engine_lifecycle.py`` — Engine uses router internally
    - ``src/spine/execution/runtimes/router.py`` — Implementation
"""

import asyncio

from spine.execution.runtimes import (
    ContainerJobSpec,
    JobError,
    LocalProcessAdapter,
    RuntimeAdapterRouter,
    StubRuntimeAdapter,
)


# ── Section 1: Register multiple adapters ─────────────────────────────────

def demo_register():
    """Register adapters and inspect the registry."""
    print("=" * 70)
    print("SECTION 1 — Register Multiple Adapters")
    print("=" * 70)

    router = RuntimeAdapterRouter()

    # Register two adapters
    local = LocalProcessAdapter()
    stub = StubRuntimeAdapter(auto_succeed=True)

    router.register(local)
    router.register(stub)

    registered = router.list_runtimes()
    print(f"  Registered: {registered}")
    assert "local" in registered
    assert "stub" in registered
    print("  ✓ Both adapters registered\n")
    return router


# ── Section 2: Default selection ──────────────────────────────────────────

def demo_default(router):
    """First registered adapter becomes the default."""
    print("=" * 70)
    print("SECTION 2 — Auto Default (First Registered)")
    print("=" * 70)

    print(f"  Default:     {router.default_name}")
    assert router.default_name == "local"
    print("  ✓ First-registered adapter is default\n")


# ── Section 3: Override default ───────────────────────────────────────────

def demo_set_default(router):
    """Explicitly set a different default."""
    print("=" * 70)
    print("SECTION 3 — Override Default")
    print("=" * 70)

    router.set_default("stub")
    print(f"  New default: {router.default_name}")
    assert router.default_name == "stub"

    # Route without spec.runtime → uses new default
    spec = ContainerJobSpec(
        name="default-test",
        image="python:3.12",
        command=["echo", "test"],
    )
    adapter = router.route(spec)
    print(f"  Routed to:   {adapter.runtime_name}")
    assert adapter.runtime_name == "stub"
    print("  ✓ Default overridden\n")

    # Restore original
    router.set_default("local")


# ── Section 4: Spec-based routing ─────────────────────────────────────────

def demo_spec_routing(router):
    """Pin a spec to a specific runtime."""
    print("=" * 70)
    print("SECTION 4 — Spec-Based Routing")
    print("=" * 70)

    # Explicit runtime = "stub" bypasses default
    spec_pinned = ContainerJobSpec(
        name="pinned-job",
        image="python:3.12",
        command=["echo", "hello"],
        runtime="stub",
    )

    spec_default = ContainerJobSpec(
        name="default-job",
        image="python:3.12",
        command=["echo", "hello"],
    )

    adapter_pinned = router.route(spec_pinned)
    adapter_default = router.route(spec_default)

    print(f"  Pinned spec  → {adapter_pinned.runtime_name}")
    print(f"  Default spec → {adapter_default.runtime_name}")
    assert adapter_pinned.runtime_name == "stub"
    assert adapter_default.runtime_name == "local"
    print("  ✓ Routing works correctly\n")


# ── Section 5: Unregister ─────────────────────────────────────────────────

def demo_unregister(router):
    """Remove an adapter from the registry."""
    print("=" * 70)
    print("SECTION 5 — Unregister Adapter")
    print("=" * 70)

    before = router.list_runtimes()
    print(f"  Before:  {before}")

    removed = router.unregister("stub")
    after = router.list_runtimes()
    print(f"  Removed: {removed}")
    print(f"  After:   {after}")

    assert removed is True
    assert "stub" not in after
    print("  ✓ Adapter unregistered\n")

    # Re-register for later demos
    stub = StubRuntimeAdapter(auto_succeed=True)
    router.register(stub)


# ── Section 6: Aggregate health checks ────────────────────────────────────

def demo_health_all(router):
    """Check health of all registered adapters at once."""
    print("=" * 70)
    print("SECTION 6 — Aggregate Health (health_all)")
    print("=" * 70)

    async def run():
        health_map = await router.health_all()
        for name, health in health_map.items():
            print(f"  {name:10s}  healthy={health.healthy}  "
                  f"version={health.version}")

        assert all(h.healthy for h in health_map.values())
        print("  ✓ All adapters healthy\n")

    asyncio.run(run())


# ── Section 7: Unknown runtime error ──────────────────────────────────────

def demo_unknown_runtime(router):
    """Route to an unregistered runtime raises JobError."""
    print("=" * 70)
    print("SECTION 7 — Unknown Runtime Error")
    print("=" * 70)

    spec = ContainerJobSpec(
        name="mystery-job",
        image="python:3.12",
        command=["echo", "hello"],
        runtime="kubernetes",  # Not registered!
    )

    try:
        router.route(spec)
        print("  ERROR: Should have raised!")
    except (JobError, KeyError, ValueError) as e:
        print(f"  Exception:   {type(e).__name__}: {e}")
        print("  ✓ Unknown runtime correctly rejected\n")


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    router = demo_register()
    demo_default(router)
    demo_set_default(router)
    demo_spec_routing(router)
    demo_unregister(router)
    demo_health_all(router)
    demo_unknown_runtime(router)
    print("=" * 70)
    print("ALL SECTIONS PASSED ✓")
    print("=" * 70)
