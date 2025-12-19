"""
PipelineRunner — Executing pipelines by name.

WHY A RUNNER
────────────
Hard-coding `MyPipeline(params).run()` couples the caller to a
concrete class.  PipelineRunner accepts a *name* string, looks up
the class from the registry, validates params, runs it, and handles
exceptions — turning crashes into PipelineResult(FAILED).

This is the same name-based dispatch that the **Workflow** engine
(spine.orchestration) uses internally via Step.pipeline("name").
Understanding PipelineRunner helps you debug how workflows actually
execute each step under the hood.

ARCHITECTURE
────────────
    caller ──▶ runner.run("demo.ingest", params)
                │
                ├─ Registry lookup   → Pipeline class
                ├─ Instantiate       → Pipeline(params=...)
                ├─ validate_params() → raise on bad input
                ├─ run()             → PipelineResult
                └─ catch exceptions  → PipelineResult(FAILED)

    runner.run_all(["a", "b", "c"])  → [Result, Result, Result]

PIPELINE CHAINING vs WORKFLOWS
──────────────────────────────
    # Manual chaining (this example):
    ingest = runner.run("demo.ingest", {"source": "api"})
    if ingest.status == COMPLETED:
        rows = ingest.metrics["rows_ingested"]
        runner.run("demo.transform", {"input_rows": rows})

    # Preferred: Workflow with automatic data passing:
    workflow = Workflow("demo.etl", steps=[
        Step.pipeline("ingest", "demo.ingest"),
        Step.pipeline("transform", "demo.transform"),
    ])  # → context passes data between steps automatically

    Manual chaining works for scripts and notebooks.  For
    production, use Workflows to get retry, persistence, and
    failure-policy handling for free.

BEST PRACTICES
──────────────
• Always check result.status before chaining.
• Use run_all() for independent pipelines in sequence.
• Prefer runner.run() over direct instantiation for consistency.
• For multi-step chains, prefer Workflow (04_orchestration/).

Run: python examples/08_framework/02_pipeline_runner.py

See Also:
    01_pipeline_basics — defining Pipeline subclasses
    03_pipeline_registry — how name → class lookup works
    04_orchestration/01_workflow_basics — compose instead of chaining
    04_orchestration/12_managed_workflow — zero-coupling workflow builder
"""

from datetime import datetime, timezone
from typing import Any

from spine.framework import (
    Pipeline,
    PipelineResult,
    PipelineStatus,
    PipelineRunner,
    register_pipeline,
    clear_registry,
)


# Define and register pipelines
@register_pipeline("demo.ingest")
class IngestPipeline(Pipeline):
    """Ingests data from a source."""
    
    name = "demo.ingest"
    description = "Ingest data from external source"
    
    def run(self) -> PipelineResult:
        started_at = datetime.now(timezone.utc)
        
        source = self.params.get("source", "default")
        
        # Simulate ingestion
        rows = 1000
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics={"source": source, "rows_ingested": rows},
        )


@register_pipeline("demo.transform")
class TransformPipeline(Pipeline):
    """Transforms ingested data."""
    
    name = "demo.transform"
    description = "Transform and normalize data"
    
    def run(self) -> PipelineResult:
        started_at = datetime.now(timezone.utc)
        
        input_rows = self.params.get("input_rows", 1000)
        
        # Simulate transformation
        output_rows = int(input_rows * 0.95)  # 5% filtered
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics={
                "input_rows": input_rows,
                "output_rows": output_rows,
                "filtered": input_rows - output_rows,
            },
        )


@register_pipeline("demo.failing")
class FailingPipeline(Pipeline):
    """A pipeline that always fails."""
    
    name = "demo.failing"
    description = "Pipeline that demonstrates failure"
    
    def run(self) -> PipelineResult:
        raise RuntimeError("Simulated pipeline failure")


def main():
    """Demonstrate PipelineRunner for pipeline execution."""
    print("=" * 60)
    print("PipelineRunner - Executing Pipelines by Name")
    print("=" * 60)
    
    # Create runner
    runner = PipelineRunner()
    
    print("\n1. Running a pipeline by name...")
    
    result = runner.run("demo.ingest", params={"source": "api"})
    
    print(f"   Pipeline: demo.ingest")
    print(f"   Status: {result.status.value}")
    print(f"   Metrics: {result.metrics}")
    
    print("\n2. Running with parameters...")
    
    result2 = runner.run("demo.transform", params={"input_rows": 5000})
    
    print(f"   Pipeline: demo.transform")
    print(f"   Status: {result2.status.value}")
    print(f"   Input rows: {result2.metrics['input_rows']}")
    print(f"   Output rows: {result2.metrics['output_rows']}")
    print(f"   Filtered: {result2.metrics['filtered']}")
    
    print("\n3. Running non-existent pipeline...")
    
    try:
        runner.run("nonexistent.pipeline")
    except Exception as e:
        print(f"   ✓ Caught error: {type(e).__name__}")
        print(f"     {e}")
    
    print("\n4. Handling pipeline failures...")
    
    result3 = runner.run("demo.failing")
    
    print(f"   Status: {result3.status.value}")
    print(f"   Error: {result3.error}")
    
    print("\n5. Running multiple pipelines in sequence...")
    
    results = runner.run_all(
        ["demo.ingest", "demo.transform"],
        params={"source": "batch"},
    )
    
    print(f"   Ran {len(results)} pipelines:")
    for i, r in enumerate(results):
        print(f"     {i+1}. {r.status.value}")
    
    print("\n6. Pipeline chaining pattern...")
    
    # Run ingest, use its output for transform
    ingest_result = runner.run("demo.ingest", params={"source": "file"})
    
    if ingest_result.status == PipelineStatus.COMPLETED:
        rows = ingest_result.metrics.get("rows_ingested", 0)
        transform_result = runner.run("demo.transform", params={"input_rows": rows})
        
        print(f"   Ingest: {ingest_result.metrics['rows_ingested']} rows")
        print(f"   Transform: {transform_result.metrics['output_rows']} rows")
    
    print("\n" + "=" * 60)
    print("PipelineRunner demo complete!")


if __name__ == "__main__":
    # Clear registry first (in case of re-runs)
    clear_registry()
    
    # Re-register pipelines
    register_pipeline("demo.ingest")(IngestPipeline)
    register_pipeline("demo.transform")(TransformPipeline)
    register_pipeline("demo.failing")(FailingPipeline)
    
    main()
