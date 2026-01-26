"""
Pattern 02: Pipeline Sequence (No Workflow Needed)

Use this pattern when:
- Multiple operations in order
- NO validation needed between steps
- NO data passing between steps (each reads from source)
- Simple "run A, then B, then C"

If you need validation or data passing, use Workflow instead!

Run: uv run python -m examples.patterns.02_pipeline_sequence
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


# =============================================================================
# Base Pipeline Class
# =============================================================================

class Pipeline(ABC):
    """Base class for all pipelines."""
    
    name: str = ""
    description: str = ""
    
    @abstractmethod
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the pipeline with given parameters."""
        ...


# =============================================================================
# Pipelines for a Simple ETL Sequence
# =============================================================================

class ExtractPipeline(Pipeline):
    """Extract data from source."""
    
    name = "etl.extract"
    description = "Extract data from source system"
    
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        source = params["source"]
        
        # Simulated extraction
        print(f"    Extracting from {source}...")
        
        return {
            "source": source,
            "records": 1000,
            "extracted_at": datetime.now().isoformat(),
        }


class TransformPipeline(Pipeline):
    """Transform extracted data."""
    
    name = "etl.transform"
    description = "Transform and clean data"
    
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        # This pipeline reads from staging, not from previous step
        
        # Simulated transformation
        print(f"    Transforming data...")
        
        return {
            "records_in": 1000,
            "records_out": 980,
            "records_rejected": 20,
            "transformed_at": datetime.now().isoformat(),
        }


class LoadPipeline(Pipeline):
    """Load data to destination."""
    
    name = "etl.load"
    description = "Load data to destination"
    
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        destination = params["destination"]
        
        # This pipeline reads from staging, not from previous step
        
        # Simulated load
        print(f"    Loading to {destination}...")
        
        return {
            "destination": destination,
            "records_loaded": 980,
            "loaded_at": datetime.now().isoformat(),
        }


# =============================================================================
# Simple Sequential Runner (No Workflow Overhead)
# =============================================================================

def run_pipeline_sequence(
    pipelines: list[Pipeline],
    params: dict[str, Any],
    stop_on_error: bool = True,
) -> list[dict[str, Any]]:
    """
    Run pipelines in sequence.
    
    This is the SIMPLEST orchestration pattern:
    - No data passing between steps
    - No validation between steps
    - Just run A, then B, then C
    
    Use this when:
    - Each pipeline is independent
    - Each reads from its own source (DB, staging table, etc.)
    - You don't need quality gates between steps
    """
    results = []
    
    for pipeline in pipelines:
        print(f"  Running: {pipeline.name}")
        
        try:
            result = pipeline.execute(params)
            results.append({
                "pipeline": pipeline.name,
                "status": "completed",
                "result": result,
            })
            
        except Exception as e:
            results.append({
                "pipeline": pipeline.name,
                "status": "failed",
                "error": str(e),
            })
            
            if stop_on_error:
                print(f"  STOPPED: {pipeline.name} failed")
                break
    
    return results


# =============================================================================
# Demo
# =============================================================================

def demo_pipeline_sequence():
    """Demonstrate simple pipeline sequence."""
    
    print("=" * 60)
    print("PATTERN 02: Pipeline Sequence (No Workflow)")
    print("=" * 60)
    print()
    
    # Define the sequence
    pipelines = [
        ExtractPipeline(),
        TransformPipeline(),
        LoadPipeline(),
    ]
    
    # Run with shared params
    params = {
        "source": "finra_api",
        "destination": "analytics_db",
    }
    
    print("Running ETL sequence:")
    results = run_pipeline_sequence(pipelines, params)
    
    print()
    print("Results:")
    for r in results:
        status = "✓" if r["status"] == "completed" else "✗"
        print(f"  {status} {r['pipeline']}: {r['status']}")
    
    print()
    print("=" * 60)
    print("WHEN TO USE THIS PATTERN:")
    print("  ✓ Simple A → B → C execution")
    print("  ✓ Each pipeline reads from its own source")
    print("  ✓ No validation needed between steps")
    print("  ✓ No data passing between steps")
    print()
    print("WHEN TO USE WORKFLOW INSTEAD:")
    print("  → Need to validate output before continuing")
    print("  → Need to pass data from step A to step B")
    print("  → Need conditional branching")
    print("  → Need quality gates")
    print("=" * 60)


# =============================================================================
# Alternative: Using spine-core's PipelineRunner
# =============================================================================

def demo_with_runner():
    """
    Using spine-core's runner for sequential execution.
    
    This is what the CLI does under the hood.
    """
    print()
    print("Alternative: Using PipelineRunner.run_all()")
    print("-" * 40)
    print("""
    from spine.framework import get_runner
    
    runner = get_runner()
    results = runner.run_all(
        pipeline_names=["etl.extract", "etl.transform", "etl.load"],
        params={"source": "finra_api"},
    )
    
    # Stops on first failure automatically
    """)


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    demo_pipeline_sequence()
    demo_with_runner()
