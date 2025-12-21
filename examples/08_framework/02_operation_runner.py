"""
OperationRunner — Executing operations by name.

WHY A RUNNER
────────────
Hard-coding `MyOperation(params).run()` couples the caller to a
concrete class.  OperationRunner accepts a *name* string, looks up
the class from the registry, validates params, runs it, and handles
exceptions — turning crashes into OperationResult(FAILED).

This is the same name-based dispatch that the **Workflow** engine
(spine.orchestration) uses internally via Step.operation("name").
Understanding OperationRunner helps you debug how workflows actually
execute each step under the hood.

ARCHITECTURE
────────────
    caller ──▶ runner.run("demo.ingest", params)
                │
                ├─ Registry lookup   → Operation class
                ├─ Instantiate       → Operation(params=...)
                ├─ validate_params() → raise on bad input
                ├─ run()             → OperationResult
                └─ catch exceptions  → OperationResult(FAILED)

    runner.run_all(["a", "b", "c"])  → [Result, Result, Result]

operation CHAINING vs WORKFLOWS
──────────────────────────────
    # Manual chaining (this example):
    ingest = runner.run("demo.ingest", {"source": "api"})
    if ingest.status == COMPLETED:
        rows = ingest.metrics["rows_ingested"]
        runner.run("demo.transform", {"input_rows": rows})

    # Preferred: Workflow with automatic data passing:
    workflow = Workflow("demo.etl", steps=[
        Step.operation("ingest", "demo.ingest"),
        Step.operation("transform", "demo.transform"),
    ])  # → context passes data between steps automatically

    Manual chaining works for scripts and notebooks.  For
    production, use Workflows to get retry, persistence, and
    failure-policy handling for free.

BEST PRACTICES
──────────────
• Always check result.status before chaining.
• Use run_all() for independent operations in sequence.
• Prefer runner.run() over direct instantiation for consistency.
• For multi-step chains, prefer Workflow (04_orchestration/).

Run: python examples/08_framework/02_operation_runner.py

See Also:
    01_operation_basics — defining Operation subclasses
    03_operation_registry — how name → class lookup works
    04_orchestration/01_workflow_basics — compose instead of chaining
    04_orchestration/12_managed_workflow — zero-coupling workflow builder
"""

from datetime import datetime, timezone
from typing import Any

from spine.framework import (
    Operation,
    OperationResult,
    OperationStatus,
    OperationRunner,
    register_operation,
    clear_registry,
)


# Define and register operations
@register_operation("demo.ingest")
class IngestOperation(Operation):
    """Ingests data from a source."""
    
    name = "demo.ingest"
    description = "Ingest data from external source"
    
    def run(self) -> OperationResult:
        started_at = datetime.now(timezone.utc)
        
        source = self.params.get("source", "default")
        
        # Simulate ingestion
        rows = 1000
        
        return OperationResult(
            status=OperationStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics={"source": source, "rows_ingested": rows},
        )


@register_operation("demo.transform")
class TransformOperation(Operation):
    """Transforms ingested data."""
    
    name = "demo.transform"
    description = "Transform and normalize data"
    
    def run(self) -> OperationResult:
        started_at = datetime.now(timezone.utc)
        
        input_rows = self.params.get("input_rows", 1000)
        
        # Simulate transformation
        output_rows = int(input_rows * 0.95)  # 5% filtered
        
        return OperationResult(
            status=OperationStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics={
                "input_rows": input_rows,
                "output_rows": output_rows,
                "filtered": input_rows - output_rows,
            },
        )


@register_operation("demo.failing")
class FailingOperation(Operation):
    """A operation that always fails."""
    
    name = "demo.failing"
    description = "Operation that demonstrates failure"
    
    def run(self) -> OperationResult:
        raise RuntimeError("Simulated operation failure")


def main():
    """Demonstrate OperationRunner for operation execution."""
    print("=" * 60)
    print("OperationRunner - Executing Operations by Name")
    print("=" * 60)
    
    # Create runner
    runner = OperationRunner()
    
    print("\n1. Running a operation by name...")
    
    result = runner.run("demo.ingest", params={"source": "api"})
    
    print(f"   Operation: demo.ingest")
    print(f"   Status: {result.status.value}")
    print(f"   Metrics: {result.metrics}")
    
    print("\n2. Running with parameters...")
    
    result2 = runner.run("demo.transform", params={"input_rows": 5000})
    
    print(f"   Operation: demo.transform")
    print(f"   Status: {result2.status.value}")
    print(f"   Input rows: {result2.metrics['input_rows']}")
    print(f"   Output rows: {result2.metrics['output_rows']}")
    print(f"   Filtered: {result2.metrics['filtered']}")
    
    print("\n3. Running non-existent operation...")
    
    try:
        runner.run("nonexistent.operation")
    except Exception as e:
        print(f"   ✓ Caught error: {type(e).__name__}")
        print(f"     {e}")
    
    print("\n4. Handling operation failures...")
    
    result3 = runner.run("demo.failing")
    
    print(f"   Status: {result3.status.value}")
    print(f"   Error: {result3.error}")
    
    print("\n5. Running multiple operations in sequence...")
    
    results = runner.run_all(
        ["demo.ingest", "demo.transform"],
        params={"source": "batch"},
    )
    
    print(f"   Ran {len(results)} operations:")
    for i, r in enumerate(results):
        print(f"     {i+1}. {r.status.value}")
    
    print("\n6. Operation chaining pattern...")
    
    # Run ingest, use its output for transform
    ingest_result = runner.run("demo.ingest", params={"source": "file"})
    
    if ingest_result.status == OperationStatus.COMPLETED:
        rows = ingest_result.metrics.get("rows_ingested", 0)
        transform_result = runner.run("demo.transform", params={"input_rows": rows})
        
        print(f"   Ingest: {ingest_result.metrics['rows_ingested']} rows")
        print(f"   Transform: {transform_result.metrics['output_rows']} rows")
    
    print("\n" + "=" * 60)
    print("OperationRunner demo complete!")


if __name__ == "__main__":
    # Clear registry first (in case of re-runs)
    clear_registry()
    
    # Re-register operations
    register_operation("demo.ingest")(IngestOperation)
    register_operation("demo.transform")(TransformOperation)
    register_operation("demo.failing")(FailingOperation)
    
    main()
