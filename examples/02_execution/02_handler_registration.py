#!/usr/bin/env python3
"""Handler Registration — Mapping WorkSpecs to Executable Functions.

================================================================================
WHY A HANDLER REGISTRY?
================================================================================

When the dispatcher receives ``WorkSpec(name="fetch_filing")``, it needs to
find the actual Python function to run.  The HandlerRegistry provides this
mapping::

    registry = HandlerRegistry()

    @register_task("fetch_filing", registry=registry)
    async def fetch_filing(params: dict) -> dict:
        ...

    # Later:
    handler = registry.get("fetch_filing")  # → fetch_filing function

Without a registry, you'd need giant if/elif chains::

    # BAD — unscalable, can't introspect
    if spec.name == "fetch_filing":
        return await fetch_filing(spec.params)
    elif spec.name == "normalize_data":
        return await normalize_data(spec.params)
    # ... 50 more elif branches


================================================================================
REGISTRATION METHODS
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Method 1: Decorator (recommended)                                      │
    │                                                                         │
    │  @register_task("fetch_filing", registry=registry)                     │
    │  async def fetch_filing(params: dict) -> dict: ...                     │
    │                                                                         │
    │  @register_pipeline("daily_ingest", registry=registry)                 │
    │  async def daily_ingest(params: dict) -> dict: ...                     │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  Method 2: Explicit registration                                        │
    │                                                                         │
    │  registry.register("fetch_filing", fetch_filing,                       │
    │                     kind="task", description="Fetch SEC filing")       │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  Method 3: Auto-discovery (convention-based)                            │
    │                                                                         │
    │  registry.discover("mypackage.handlers")                               │
    │  # Finds all @register_task decorated functions in module              │
    └─────────────────────────────────────────────────────────────────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/02_execution/02_handler_registration.py

See Also:
    - :mod:`spine.execution` — HandlerRegistry, register_task, register_pipeline
    - ``examples/02_execution/01_workspec_basics.py`` — WorkSpec creation
    - ``examples/02_execution/03_dispatcher_basics.py`` — Dispatching work
"""
from spine.execution import HandlerRegistry, register_task, register_pipeline


# Create a registry instance
registry = HandlerRegistry()


# === Method 1: Decorator-based registration ===

@register_task("greet_user", registry=registry, description="Greet a user by name")
async def greet_user(params: dict) -> dict:
    """Simple greeting task."""
    name = params.get("name", "World")
    return {"message": f"Hello, {name}!"}


@register_task("add_numbers", registry=registry, tags={"domain": "math"})
async def add_numbers(params: dict) -> dict:
    """Add two numbers together."""
    a = params.get("a", 0)
    b = params.get("b", 0)
    return {"result": a + b, "operation": f"{a} + {b}"}


@register_pipeline("data_pipeline", registry=registry)
async def data_pipeline(params: dict) -> dict:
    """A simple data processing pipeline."""
    steps = params.get("steps", [])
    return {"pipeline": "data_pipeline", "steps_count": len(steps)}


# === Method 2: Manual registration ===

async def manual_task(params: dict) -> dict:
    """A manually registered task."""
    return {"status": "ok", "source": "manual"}


def main():
    print("=" * 60)
    print("Handler Registration")
    print("=" * 60)
    
    # Register manually
    registry.register(
        kind="task",
        name="manual_task",
        handler=manual_task,
        description="Manually registered task",
        tags={"type": "manual"},
    )
    
    # === 1. List all registered handlers ===
    print("\n[1] All Registered Handlers")
    for metadata in registry.list_with_metadata():
        kind = metadata["kind"]
        name = metadata["name"]
        tags = metadata.get("tags", {})
        description = metadata.get("description")
        print(f"  {kind}:{name}")
        if description:
            print(f"    Description: {description}")
        if tags:
            print(f"    Tags: {tags}")
    
    # === 2. Look up specific handler ===
    print("\n[2] Handler Lookup")
    if registry.has("task", "greet_user"):
        handler = registry.get("task", "greet_user")
        metadata = registry.get_metadata("task", "greet_user")
        print(f"  Found: task:greet_user")
        print(f"  Handler: {handler.__name__}")
        print(f"  Description: {metadata.get('description') if metadata else 'N/A'}")
    
    # === 3. Filter by tags ===
    print("\n[3] Filter by Tags")
    math_handlers = [
        m for m in registry.list_with_metadata()
        if m.get("tags", {}).get("domain") == "math"
    ]
    print(f"  Handlers with domain=math: {len(math_handlers)}")
    for m in math_handlers:
        print(f"    - {m['kind']}:{m['name']}")
    
    # === 4. Check handler exists ===
    print("\n[4] Handler Existence Check")
    exists = registry.has("task", "greet_user")
    print(f"  task:greet_user exists: {exists}")
    
    missing = registry.has("task", "nonexistent")
    print(f"  task:nonexistent exists: {missing}")
    
    # === 5. Build handler map for executor ===
    print("\n[5] Build Handler Map")
    handler_map = registry.to_executor_handlers()
    print(f"  Handler map has {len(handler_map)} entries")
    for key in handler_map:
        print(f"    - {key}")
    
    print("\n" + "=" * 60)
    print("[OK] Handler Registration Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
