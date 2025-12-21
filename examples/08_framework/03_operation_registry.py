"""
Operation Registry — Registering and discovering operations.

WHY A REGISTRY
──────────────
Without a registry, adding a new operation means editing a dispatch
table somewhere.  The registry lets you decorate a class with
@register_operation("name") and it's instantly available to
OperationRunner, CLI commands, API endpoints, **and the Workflow
engine** — Step.operation("name") resolves through this same registry.

TWO REGISTRIES IN SPINE
───────────────────────
    Registry               Module               Stores
    ────────────────────── ──────────────────── ──────────────────────
    Operation Registry      spine.framework      Operation subclasses
    Workflow Registry      spine.orchestration   Workflow definitions

    @register_operation("finra.otc.ingest")  ← this example
    @register_workflow("finra.weekly")       ← 04_orchestration/12

    Both use the same pattern: dotted names, decorator registration,
    KeyError on lookup failure, clear_*() for test isolation.

ARCHITECTURE
────────────
    @register_operation("finra.otc.ingest")
    class OTCIngestOperation(Operation): ...
         │
         ▼
    ┌────────────────────────────────────┐
    │ Global Operation Registry           │
    │  {"finra.otc.ingest": OTCIngest..} │
    │  {"finra.otc.normalize": OTCNorm..}│
    │  {"sec.filings.ingest": SECFili..} │
    └─────────────┬──────────────────────┘
                  │
       ┌──────────┼────────────┐
       ▼          ▼            ▼
    get_operation  list_operations  clear_registry
    ("name")      ()               ()
       │
       └──── also used by ────▶  Step.operation("name")
                                  inside Workflows

    list_operations() enables domain-prefix discovery:
    finra_pipes = [p for p in list_operations() if p.startswith("finra.")]

BEST PRACTICES
──────────────
• Use dotted, lowercase names: "domain.subsystem.verb".
• Duplicate names raise ValueError — catch at startup.
• Call clear_registry() in tests to avoid cross-test leaks.
• Use list_operations() to build dynamic CLI menus.
• Register operations early — before building Workflows that reference them.

Run: python examples/08_framework/03_operation_registry.py

See Also:
    01_operation_basics — Operation base class
    02_operation_runner — executing registered operations
    04_orchestration/10_workflow_registry_yaml — the Workflow registry
"""

from datetime import datetime, timezone

from spine.framework import (
    Operation,
    OperationResult,
    OperationStatus,
    register_operation,
    get_operation,
    list_operations,
    clear_registry,
)


def main():
    """Demonstrate operation registry for discovery."""
    print("=" * 60)
    print("Operation Registry - Registration and Discovery")
    print("=" * 60)
    
    # Clear registry for clean demo
    clear_registry()
    
    print("\n1. Registering operations with decorator...")
    
    @register_operation("finra.otc.ingest")
    class OTCIngestOperation(Operation):
        """Ingest OTC transparency data."""
        
        name = "finra.otc.ingest"
        description = "Ingest FINRA OTC transparency data"
        
        def run(self) -> OperationResult:
            return OperationResult(
                status=OperationStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                metrics={"rows": 1000},
            )
    
    @register_operation("finra.otc.normalize")
    class OTCNormalizeOperation(Operation):
        """Normalize OTC data."""
        
        name = "finra.otc.normalize"
        description = "Normalize FINRA OTC data"
        
        def run(self) -> OperationResult:
            return OperationResult(
                status=OperationStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
    
    @register_operation("sec.filings.ingest")
    class SECFilingsOperation(Operation):
        """Ingest SEC filings."""
        
        name = "sec.filings.ingest"
        description = "Ingest SEC EDGAR filings"
        
        def run(self) -> OperationResult:
            return OperationResult(
                status=OperationStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
    
    print("   ✓ Registered 3 operations")
    
    print("\n2. Listing registered operations...")
    
    operations = list_operations()
    print(f"   Found {len(operations)} operations:")
    for name in operations:
        print(f"     - {name}")
    
    print("\n3. Getting a operation by name...")
    
    operation_cls = get_operation("finra.otc.ingest")
    print(f"   Got: {operation_cls.__name__}")
    print(f"   Description: {operation_cls.description}")
    
    # Instantiate and run
    operation = operation_cls(params={"tier": "NMS_TIER_1"})
    result = operation.run()
    print(f"   Executed: {result.status.value}")
    
    print("\n4. Handling unknown operations...")
    
    try:
        get_operation("nonexistent.operation")
    except KeyError as e:
        print(f"   ✓ KeyError raised for unknown operation")
        print(f"     {e}")
    
    print("\n5. Preventing duplicate registration...")
    
    try:
        @register_operation("finra.otc.ingest")  # Already registered!
        class DuplicateOperation(Operation):
            def run(self):
                pass
    except ValueError as e:
        print(f"   ✓ ValueError raised for duplicate")
        print(f"     {e}")
    
    print("\n6. Operation discovery pattern...")
    
    # Find all operations in a domain
    finra_operations = [p for p in list_operations() if p.startswith("finra.")]
    sec_operations = [p for p in list_operations() if p.startswith("sec.")]
    
    print(f"   FINRA domain: {finra_operations}")
    print(f"   SEC domain: {sec_operations}")
    
    print("\n7. Dynamic operation execution...")
    
    # Execute all operations in a domain
    print("   Running all FINRA operations:")
    for name in finra_operations:
        cls = get_operation(name)
        instance = cls(params={})
        result = instance.run()
        print(f"     {name}: {result.status.value}")
    
    print("\n8. Registry cleanup...")
    
    clear_registry()
    print(f"   Cleared registry")
    print(f"   Operations remaining: {len(list_operations())}")
    
    print("\n" + "=" * 60)
    print("Operation Registry demo complete!")


if __name__ == "__main__":
    main()
