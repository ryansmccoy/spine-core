"""
Pipeline Base Class — The building block of Spine workflows.

WHAT IS A PIPELINE?
───────────────────
A Pipeline is the smallest **unit of work** in Spine — a single,
testable operation like "download FINRA data" or "score risk".
Pipelines are building blocks; you compose them into multi-step
**Workflows** (see 04_orchestration/) for production use.

    Pipeline  = "how to do one thing well"
    Workflow  = "how to combine multiple pipelines into a reliable process"

WHY PIPELINE CLASSES
────────────────────
Raw handler functions (see 02_execution) are fine for simple tasks,
but production pipelines need:
• A standard interface so runners and registries can discover them.
• Built-in parameter validation before execution starts.
• A typed PipelineResult with status, duration, metrics, and error.

The Pipeline base class provides all three.

ARCHITECTURE
────────────
    ┌────────────────────────┐
    │ Pipeline (base class)    │  ← you subclass this
    │   name: str              │
    │   description: str       │
    │   validate_params()      │  ← optional override
    │   run() → PipelineResult │  ← required override
    └────────────┬───────────┘
               │
               ▼
    ┌────────────────────────┐
    │ PipelineResult           │
    │   status: PipelineStatus │  COMPLETED | FAILED
    │   started_at, completed_at│
    │   duration_seconds: float│
    │   metrics: dict           │
    │   error: str | None      │
    └────────────────────────┘

               ⇩  used as a step inside…

    ┌───────────────────────────────────────┐
    │ Workflow (04_orchestration)            │
    │   Step.pipeline("ingest", "finra.otc") │  ← name-based lookup
    │   Step.lambda_("validate", fn)         │
    │   Step.pipeline("normalise", "finra…") │
    └───────────────────────────────────────┘

PIPELINE → WORKFLOW PROGRESSION
───────────────────────────────
    Level 1  Pipeline class   — single unit of work (this file)
    Level 2  PipelineRunner   — execute + chain by name (02)
    Level 3  Workflow          — multi-step with context passing (04_orch/01)
    Level 4  ManagedWorkflow   — zero-coupling + persistence (04_orch/14)
    Level 5  Templates / YAML — reusable workflow patterns (04_orch/18)

    Start here (Pipeline), then graduate to Workflows when you
    need multi-step orchestration, data passing, failure policies,
    DAG parallelism, or persistent audit trails.

BEST PRACTICES
──────────────
• Use dotted names: "finra.otc.ingest", not "IngestPipeline".
• Override validate_params() for required-field checks.
• Return PipelineResult even on failure (don't raise).
• Put timing in metrics: {"rows_ingested": n, "duration_ms": d}.
• Keep pipelines focused — one pipeline per concern, compose via Workflow.

Run: python examples/08_framework/01_pipeline_basics.py

See Also:
    02_pipeline_runner — run pipelines by name
    03_pipeline_registry — register for discovery
    04_orchestration/01_workflow_basics — compose pipelines into workflows
    04_orchestration/12_managed_workflow — import functions, full lifecycle
"""

from datetime import datetime, timezone
from typing import Any

from spine.framework import Pipeline, PipelineResult, PipelineStatus


class SimplePipeline(Pipeline):
    """A simple example pipeline."""
    
    name = "example.simple"
    description = "A simple demonstration pipeline"
    
    def run(self) -> PipelineResult:
        """Execute the pipeline."""
        started_at = datetime.now(timezone.utc)
        
        # Access parameters
        message = self.params.get("message", "Hello, World!")
        count = self.params.get("count", 1)
        
        # Do some work
        results = []
        for i in range(count):
            results.append(f"{message} ({i + 1})")
        
        completed_at = datetime.now(timezone.utc)
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=completed_at,
            metrics={
                "items_processed": count,
                "results": results,
            },
        )


class ValidatedPipeline(Pipeline):
    """Pipeline with parameter validation."""
    
    name = "example.validated"
    description = "Pipeline that validates its parameters"
    
    def validate_params(self) -> None:
        """Validate required parameters."""
        if "source" not in self.params:
            raise ValueError("Missing required parameter: source")
        
        if "batch_size" in self.params:
            batch_size = self.params["batch_size"]
            if not isinstance(batch_size, int) or batch_size < 1:
                raise ValueError("batch_size must be a positive integer")
    
    def run(self) -> PipelineResult:
        """Execute the pipeline."""
        started_at = datetime.now(timezone.utc)
        
        source = self.params["source"]
        batch_size = self.params.get("batch_size", 100)
        
        # Simulate processing
        processed = batch_size
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics={
                "source": source,
                "batch_size": batch_size,
                "processed": processed,
            },
        )


class FailablePipeline(Pipeline):
    """Pipeline that can fail based on parameters."""
    
    name = "example.failable"
    description = "Pipeline that demonstrates failure handling"
    
    def run(self) -> PipelineResult:
        """Execute the pipeline."""
        started_at = datetime.now(timezone.utc)
        
        should_fail = self.params.get("fail", False)
        
        if should_fail:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                error="Intentional failure for demonstration",
            )
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics={"success": True},
        )


def main():
    """Demonstrate Pipeline base class usage."""
    print("=" * 60)
    print("Pipeline Base Class - Creating Custom Pipelines")
    print("=" * 60)
    
    print("\n1. Simple pipeline execution...")
    
    pipeline = SimplePipeline(params={"message": "Processing", "count": 3})
    result = pipeline.run()
    
    print(f"   Status: {result.status.value}")
    print(f"   Duration: {result.duration_seconds:.4f}s")
    print(f"   Metrics: {result.metrics}")
    
    print("\n2. Pipeline with validation...")
    
    # Valid parameters
    validated = ValidatedPipeline(params={"source": "api", "batch_size": 50})
    validated.validate_params()  # No error
    result2 = validated.run()
    
    print(f"   Status: {result2.status.value}")
    print(f"   Metrics: {result2.metrics}")
    
    # Invalid parameters
    print("\n   Testing invalid parameters:")
    try:
        invalid = ValidatedPipeline(params={})  # Missing 'source'
        invalid.validate_params()
    except ValueError as e:
        print(f"   ✓ Caught validation error: {e}")
    
    try:
        invalid2 = ValidatedPipeline(params={"source": "api", "batch_size": -1})
        invalid2.validate_params()
    except ValueError as e:
        print(f"   ✓ Caught validation error: {e}")
    
    print("\n3. Failure handling...")
    
    # Successful execution
    success = FailablePipeline(params={"fail": False})
    result3 = success.run()
    print(f"   Success case: {result3.status.value}")
    
    # Failed execution
    failure = FailablePipeline(params={"fail": True})
    result4 = failure.run()
    print(f"   Failure case: {result4.status.value}")
    print(f"   Error: {result4.error}")
    
    print("\n4. Pipeline status values...")
    
    for status in PipelineStatus:
        print(f"   {status.name}: {status.value}")
    
    print("\n5. Pipeline metadata...")
    
    print(f"   Name: {SimplePipeline.name}")
    print(f"   Description: {SimplePipeline.description}")
    print(f"   Repr: {pipeline}")
    
    print("\n" + "=" * 60)
    print("Pipeline basics demo complete!")


if __name__ == "__main__":
    main()
