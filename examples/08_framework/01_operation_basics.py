"""
Operation Base Class — The building block of Spine workflows.

WHAT IS A operation?
───────────────────
A Operation is the smallest **unit of work** in Spine — a single,
testable operation like "download FINRA data" or "score risk".
Operations are building blocks; you compose them into multi-step
**Workflows** (see 04_orchestration/) for production use.

    Operation  = "how to do one thing well"
    Workflow  = "how to combine multiple operations into a reliable process"

WHY operation CLASSES
────────────────────
Raw handler functions (see 02_execution) are fine for simple tasks,
but production operations need:
• A standard interface so runners and registries can discover them.
• Built-in parameter validation before execution starts.
• A typed OperationResult with status, duration, metrics, and error.

The Operation base class provides all three.

ARCHITECTURE
────────────
    ┌────────────────────────┐
    │ Operation (base class)    │  ← you subclass this
    │   name: str              │
    │   description: str       │
    │   validate_params()      │  ← optional override
    │   run() → OperationResult │  ← required override
    └────────────┬───────────┘
               │
               ▼
    ┌────────────────────────┐
    │ OperationResult           │
    │   status: OperationStatus │  COMPLETED | FAILED
    │   started_at, completed_at│
    │   duration_seconds: float│
    │   metrics: dict           │
    │   error: str | None      │
    └────────────────────────┘

               ⇩  used as a step inside…

    ┌───────────────────────────────────────┐
    │ Workflow (04_orchestration)            │
    │   Step.operation("ingest", "finra.otc") │  ← name-based lookup
    │   Step.lambda_("validate", fn)         │
    │   Step.operation("normalise", "finra…") │
    └───────────────────────────────────────┘

operation → WORKFLOW PROGRESSION
───────────────────────────────
    Level 1  Operation class   — single unit of work (this file)
    Level 2  OperationRunner   — execute + chain by name (02)
    Level 3  Workflow          — multi-step with context passing (04_orch/01)
    Level 4  ManagedWorkflow   — zero-coupling + persistence (04_orch/14)
    Level 5  Templates / YAML — reusable workflow patterns (04_orch/18)

    Start here (Operation), then graduate to Workflows when you
    need multi-step orchestration, data passing, failure policies,
    DAG parallelism, or persistent audit trails.

BEST PRACTICES
──────────────
• Use dotted names: "finra.otc.ingest", not "IngestOperation".
• Override validate_params() for required-field checks.
• Return OperationResult even on failure (don't raise).
• Put timing in metrics: {"rows_ingested": n, "duration_ms": d}.
• Keep operations focused — one operation per concern, compose via Workflow.

Run: python examples/08_framework/01_operation_basics.py

See Also:
    02_operation_runner — run operations by name
    03_operation_registry — register for discovery
    04_orchestration/01_workflow_basics — compose operations into workflows
    04_orchestration/12_managed_workflow — import functions, full lifecycle
"""

from datetime import datetime, timezone
from typing import Any

from spine.framework import Operation, OperationResult, OperationStatus


class SimpleOperation(Operation):
    """A simple example operation."""
    
    name = "example.simple"
    description = "A simple demonstration operation"
    
    def run(self) -> OperationResult:
        """Execute the operation."""
        started_at = datetime.now(timezone.utc)
        
        # Access parameters
        message = self.params.get("message", "Hello, World!")
        count = self.params.get("count", 1)
        
        # Do some work
        results = []
        for i in range(count):
            results.append(f"{message} ({i + 1})")
        
        completed_at = datetime.now(timezone.utc)
        
        return OperationResult(
            status=OperationStatus.COMPLETED,
            started_at=started_at,
            completed_at=completed_at,
            metrics={
                "items_processed": count,
                "results": results,
            },
        )


class ValidatedOperation(Operation):
    """Operation with parameter validation."""
    
    name = "example.validated"
    description = "Operation that validates its parameters"
    
    def validate_params(self) -> None:
        """Validate required parameters."""
        if "source" not in self.params:
            raise ValueError("Missing required parameter: source")
        
        if "batch_size" in self.params:
            batch_size = self.params["batch_size"]
            if not isinstance(batch_size, int) or batch_size < 1:
                raise ValueError("batch_size must be a positive integer")
    
    def run(self) -> OperationResult:
        """Execute the operation."""
        started_at = datetime.now(timezone.utc)
        
        source = self.params["source"]
        batch_size = self.params.get("batch_size", 100)
        
        # Simulate processing
        processed = batch_size
        
        return OperationResult(
            status=OperationStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics={
                "source": source,
                "batch_size": batch_size,
                "processed": processed,
            },
        )


class FailableOperation(Operation):
    """Operation that can fail based on parameters."""
    
    name = "example.failable"
    description = "Operation that demonstrates failure handling"
    
    def run(self) -> OperationResult:
        """Execute the operation."""
        started_at = datetime.now(timezone.utc)
        
        should_fail = self.params.get("fail", False)
        
        if should_fail:
            return OperationResult(
                status=OperationStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                error="Intentional failure for demonstration",
            )
        
        return OperationResult(
            status=OperationStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics={"success": True},
        )


def main():
    """Demonstrate Operation base class usage."""
    print("=" * 60)
    print("Operation Base Class - Creating Custom Operations")
    print("=" * 60)
    
    print("\n1. Simple operation execution...")
    
    operation = SimpleOperation(params={"message": "Processing", "count": 3})
    result = operation.run()
    
    print(f"   Status: {result.status.value}")
    print(f"   Duration: {result.duration_seconds:.4f}s")
    print(f"   Metrics: {result.metrics}")
    
    print("\n2. Operation with validation...")
    
    # Valid parameters
    validated = ValidatedOperation(params={"source": "api", "batch_size": 50})
    validated.validate_params()  # No error
    result2 = validated.run()
    
    print(f"   Status: {result2.status.value}")
    print(f"   Metrics: {result2.metrics}")
    
    # Invalid parameters
    print("\n   Testing invalid parameters:")
    try:
        invalid = ValidatedOperation(params={})  # Missing 'source'
        invalid.validate_params()
    except ValueError as e:
        print(f"   ✓ Caught validation error: {e}")
    
    try:
        invalid2 = ValidatedOperation(params={"source": "api", "batch_size": -1})
        invalid2.validate_params()
    except ValueError as e:
        print(f"   ✓ Caught validation error: {e}")
    
    print("\n3. Failure handling...")
    
    # Successful execution
    success = FailableOperation(params={"fail": False})
    result3 = success.run()
    print(f"   Success case: {result3.status.value}")
    
    # Failed execution
    failure = FailableOperation(params={"fail": True})
    result4 = failure.run()
    print(f"   Failure case: {result4.status.value}")
    print(f"   Error: {result4.error}")
    
    print("\n4. Operation status values...")
    
    for status in OperationStatus:
        print(f"   {status.name}: {status.value}")
    
    print("\n5. Operation metadata...")
    
    print(f"   Name: {SimpleOperation.name}")
    print(f"   Description: {SimpleOperation.description}")
    print(f"   Repr: {operation}")
    
    print("\n" + "=" * 60)
    print("Operation basics demo complete!")


if __name__ == "__main__":
    main()
