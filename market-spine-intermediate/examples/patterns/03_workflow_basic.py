"""
Pattern 03: Basic Workflow (Orchestration with Validation)

Use this pattern when:
- Need validation BETWEEN steps
- Need to pass data FROM one step TO another
- Need quality gates before continuing
- Need observability (metrics per step)

This is the most common production pattern!

Run: uv run python -m examples.patterns.03_workflow_basic
"""

from datetime import datetime
from typing import Any
from dataclasses import dataclass
from enum import Enum


# =============================================================================
# Spine-Core Workflow Types (Simplified for Demo)
# =============================================================================

class StepType(str, Enum):
    PIPELINE = "pipeline"
    LAMBDA = "lambda"


class WorkflowStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class QualityMetrics:
    """Track data quality through the workflow."""
    records_in: int = 0
    records_out: int = 0
    records_rejected: int = 0
    
    @property
    def reject_rate(self) -> float:
        if self.records_in == 0:
            return 0.0
        return self.records_rejected / self.records_in


@dataclass
class StepResult:
    """Result of a single step."""
    success: bool
    output: dict[str, Any] | None = None
    error: str | None = None
    error_category: str | None = None
    metrics: QualityMetrics | None = None
    
    @classmethod
    def ok(cls, output: dict[str, Any] | None = None, metrics: QualityMetrics | None = None):
        return cls(success=True, output=output or {}, metrics=metrics)
    
    @classmethod
    def fail(cls, error: str, error_category: str = "UNKNOWN"):
        return cls(success=False, error=error, error_category=error_category)


class WorkflowContext:
    """Context passed between workflow steps."""
    
    def __init__(self, params: dict[str, Any]):
        self.params = params
        self._outputs: dict[str, dict[str, Any]] = {}
    
    def set_output(self, step_name: str, output: dict[str, Any]):
        """Store output from a step."""
        self._outputs[step_name] = output
    
    def get_output(self, step_name: str) -> dict[str, Any] | None:
        """Get output from a previous step."""
        return self._outputs.get(step_name)


# =============================================================================
# The Pipelines (Do the Actual Work)
# =============================================================================

def fetch_data(params: dict[str, Any]) -> dict[str, Any]:
    """Pipeline: Fetch data from source."""
    source = params.get("source", "api")
    
    # Simulated fetch
    records = [
        {"id": 1, "value": 100},
        {"id": 2, "value": 200},
        {"id": 3, "value": None},  # Bad record
        {"id": 4, "value": 150},
    ]
    
    return {
        "source": source,
        "records": records,
        "count": len(records),
        "fetched_at": datetime.now().isoformat(),
    }


def process_data(params: dict[str, Any]) -> dict[str, Any]:
    """Pipeline: Process/transform data."""
    records = params.get("records", [])
    
    # Filter out bad records
    valid = [r for r in records if r.get("value") is not None]
    rejected = len(records) - len(valid)
    
    # Transform
    processed = [{"id": r["id"], "value": r["value"] * 2} for r in valid]
    
    return {
        "processed": processed,
        "count": len(processed),
        "rejected": rejected,
    }


def store_data(params: dict[str, Any]) -> dict[str, Any]:
    """Pipeline: Store to database."""
    records = params.get("records", [])
    
    # Simulated store
    return {
        "stored": len(records),
        "stored_at": datetime.now().isoformat(),
    }


# =============================================================================
# Validation Lambda Steps (LIGHTWEIGHT - Just Check Output)
# =============================================================================

def validate_fetch(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Validate fetch output before processing.
    
    LIGHTWEIGHT: Only checks previous step's output.
    Does NOT do any data fetching or transformation.
    """
    fetch_output = ctx.get_output("fetch")
    
    if fetch_output is None:
        return StepResult.fail("Fetch step produced no output", "VALIDATION")
    
    count = fetch_output.get("count", 0)
    min_records = config.get("min_records", 1)
    
    if count < min_records:
        return StepResult.fail(
            f"Too few records: {count} < {min_records}",
            "QUALITY",
        )
    
    return StepResult.ok(
        output={"validated": True, "count": count},
        metrics=QualityMetrics(records_in=count, records_out=count),
    )


def validate_process(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Validate processing result.
    
    Checks reject rate is acceptable.
    """
    fetch_output = ctx.get_output("fetch")
    process_output = ctx.get_output("process")
    
    if process_output is None:
        return StepResult.fail("Process step produced no output", "VALIDATION")
    
    records_in = fetch_output.get("count", 0)
    records_out = process_output.get("count", 0)
    rejected = process_output.get("rejected", 0)
    
    max_reject_rate = config.get("max_reject_rate", 0.10)
    reject_rate = rejected / records_in if records_in > 0 else 0
    
    if reject_rate > max_reject_rate:
        return StepResult.fail(
            f"High reject rate: {reject_rate:.1%} > {max_reject_rate:.1%}",
            "QUALITY",
        )
    
    return StepResult.ok(
        output={"reject_rate": reject_rate, "validated": True},
        metrics=QualityMetrics(
            records_in=records_in,
            records_out=records_out,
            records_rejected=rejected,
        ),
    )


# =============================================================================
# Workflow Definition and Runner
# =============================================================================

def create_etl_workflow():
    """
    Define a workflow that orchestrates pipelines with validation.
    
    Structure:
      fetch (pipeline)
        → validate_fetch (lambda)
        → process (pipeline)
        → validate_process (lambda)
        → store (pipeline)
    """
    return {
        "name": "etl.with_validation",
        "steps": [
            # Pipeline step: actual work
            {
                "name": "fetch",
                "type": "pipeline",
                "handler": fetch_data,
            },
            # Lambda step: validate fetch output
            {
                "name": "validate_fetch",
                "type": "lambda",
                "handler": validate_fetch,
                "config": {"min_records": 2},
            },
            # Pipeline step: process data
            {
                "name": "process",
                "type": "pipeline",
                "handler": process_data,
            },
            # Lambda step: validate process output
            {
                "name": "validate_process",
                "type": "lambda",
                "handler": validate_process,
                "config": {"max_reject_rate": 0.30},
            },
            # Pipeline step: store results
            {
                "name": "store",
                "type": "pipeline",
                "handler": store_data,
            },
        ],
    }


def run_workflow(workflow: dict, params: dict) -> dict:
    """Simple workflow runner for demonstration."""
    
    ctx = WorkflowContext(params)
    results = []
    status = WorkflowStatus.COMPLETED
    error_step = None
    error_msg = None
    
    for step in workflow["steps"]:
        step_name = step["name"]
        step_type = step["type"]
        handler = step["handler"]
        config = step.get("config", {})
        
        print(f"  [{step_type:8}] {step_name}...", end=" ")
        
        try:
            if step_type == "pipeline":
                # Pipeline step: pass params + previous outputs
                step_params = {**params}
                
                # For process step, pass records from fetch
                if step_name == "process":
                    fetch_out = ctx.get_output("fetch")
                    if fetch_out:
                        step_params["records"] = fetch_out.get("records", [])
                
                # For store step, pass processed records
                if step_name == "store":
                    process_out = ctx.get_output("process")
                    if process_out:
                        step_params["records"] = process_out.get("processed", [])
                
                output = handler(step_params)
                ctx.set_output(step_name, output)
                
                print(f"✓ {output}")
                results.append({"step": step_name, "status": "completed", "output": output})
                
            elif step_type == "lambda":
                # Lambda step: validate previous output
                result = handler(ctx, config)
                
                if result.success:
                    ctx.set_output(step_name, result.output)
                    print(f"✓ {result.output}")
                    results.append({"step": step_name, "status": "completed"})
                else:
                    print(f"✗ {result.error}")
                    status = WorkflowStatus.FAILED
                    error_step = step_name
                    error_msg = result.error
                    results.append({"step": step_name, "status": "failed", "error": result.error})
                    break
                    
        except Exception as e:
            print(f"✗ Exception: {e}")
            status = WorkflowStatus.FAILED
            error_step = step_name
            error_msg = str(e)
            results.append({"step": step_name, "status": "failed", "error": str(e)})
            break
    
    return {
        "workflow": workflow["name"],
        "status": status.value,
        "error_step": error_step,
        "error": error_msg,
        "steps": results,
    }


# =============================================================================
# Demo
# =============================================================================

def demo_workflow_basic():
    """Demonstrate basic workflow pattern."""
    
    print("=" * 60)
    print("PATTERN 03: Basic Workflow")
    print("=" * 60)
    print()
    
    workflow = create_etl_workflow()
    
    print(f"Workflow: {workflow['name']}")
    print("Steps:")
    for s in workflow["steps"]:
        print(f"  - [{s['type']}] {s['name']}")
    print()
    
    print("Executing:")
    result = run_workflow(workflow, {"source": "api"})
    
    print()
    print(f"Status: {result['status']}")
    if result["error"]:
        print(f"Failed at: {result['error_step']}")
        print(f"Error: {result['error']}")
    
    print()
    print("=" * 60)
    print("KEY POINTS:")
    print("  - Pipeline steps do ACTUAL WORK (fetch, process, store)")
    print("  - Lambda steps VALIDATE between pipeline steps")
    print("  - Context passes data between steps")
    print("  - Workflow stops on validation failure")
    print("  - Each step produces metrics for observability")
    print("=" * 60)


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    demo_workflow_basic()
