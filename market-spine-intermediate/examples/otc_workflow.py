"""
OTC Workflow Example - Proper Pattern for Using Pipelines with Workflow

This example shows the CORRECT way to use existing pipelines with workflows:
1. Pipelines do the work (OTCIngestPipeline, OTCNormalizePipeline, etc.)
2. Workflow orchestrates pipelines via Step.pipeline()
3. Lambda steps do LIGHTWEIGHT validation/routing between pipeline steps

Key Point: Don't copy pipeline logic into lambda steps!
"""

from spine.orchestration import (
    Workflow,
    Step,
    StepResult,
    QualityMetrics,
    WorkflowRunner,
    WorkflowContext,
)

# Import the adapter that bridges intermediate pipelines → spine-core registry
from market_spine.orchestration.compat import register_adapted_pipelines


# =============================================================================
# Step 1: Register your intermediate pipelines with spine-core
# =============================================================================

# This bridges the gap between intermediate's registry and spine-core's registry
# Call this once at startup (e.g., in your app initialization)
register_adapted_pipelines()


# =============================================================================
# Step 2: Define validation lambda steps (LIGHTWEIGHT - no pipeline logic!)
# =============================================================================

def validate_ingest_result(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Validate the ingest step succeeded with enough records.
    
    This is LIGHTWEIGHT validation - just checking the previous step's output.
    The actual ingestion logic stays in OTCIngestPipeline.
    """
    # Get output from the previous step (ingest)
    ingest_output = ctx.get_output("ingest")
    
    if ingest_output is None:
        return StepResult.fail(
            error="Ingest step did not produce output",
            error_category="VALIDATION",
        )
    
    record_count = ingest_output.get("records", 0)
    inserted = ingest_output.get("inserted", 0)
    
    # Quality gate: require minimum records
    min_records = config.get("min_records", 100)
    
    if record_count < min_records:
        return StepResult.fail(
            error=f"Too few records: {record_count} < {min_records}",
            error_category="QUALITY",
            metrics=QualityMetrics(
                records_in=record_count,
                records_out=0,
            ),
        )
    
    return StepResult.ok(
        output={
            "validated": True,
            "record_count": record_count,
            "inserted": inserted,
        },
        metrics=QualityMetrics(
            records_in=record_count,
            records_out=record_count,
        ),
    )


def validate_normalize_result(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Validate normalization had acceptable reject rate.
    """
    normalize_output = ctx.get_output("normalize")
    
    if normalize_output is None:
        return StepResult.fail(error="Normalize step did not produce output")
    
    processed = normalize_output.get("processed", 0)
    rejected = normalize_output.get("rejected", 0)
    
    # Quality gate: reject rate < 5%
    max_reject_rate = config.get("max_reject_rate", 0.05)
    reject_rate = rejected / processed if processed > 0 else 0
    
    if reject_rate > max_reject_rate:
        return StepResult.fail(
            error=f"High reject rate: {reject_rate:.1%} > {max_reject_rate:.1%}",
            error_category="QUALITY",
        )
    
    return StepResult.ok(
        output={"reject_rate": reject_rate, "validated": True},
        metrics=QualityMetrics(
            records_in=processed,
            records_out=processed - rejected,
            records_rejected=rejected,
        ),
    )


def check_quality_grade(ctx: WorkflowContext, config: dict) -> StepResult:
    """
    Check the quality check result and decide if we should proceed.
    """
    quality_output = ctx.get_output("quality_check")
    
    if quality_output is None:
        return StepResult.fail(error="Quality check did not produce output")
    
    grade = quality_output.get("grade", "F")
    score = quality_output.get("score", 0)
    min_grade = config.get("min_grade", "C")
    
    # Grade comparison (A > B > C > D > F)
    grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
    
    if grade_order.get(grade, 0) < grade_order.get(min_grade, 3):
        return StepResult.fail(
            error=f"Quality grade {grade} below minimum {min_grade}",
            error_category="QUALITY",
        )
    
    return StepResult.ok(
        output={"grade": grade, "score": score, "passed": True}
    )


# =============================================================================
# Step 3: Create the Workflow
# =============================================================================

def create_otc_weekly_workflow() -> Workflow:
    """
    Create the OTC weekly refresh workflow.
    
    Pattern:
    - Step.pipeline() → references registered pipeline by name
    - Step.lambda_() → lightweight validation/routing ONLY
    """
    return Workflow(
        name="otc.weekly_refresh",
        domain="otc",
        description="Ingest, normalize, and summarize weekly OTC data with quality gates",
        steps=[
            # Pipeline step: actual work done by OTCIngestPipeline
            Step.pipeline(
                name="ingest",
                pipeline_name="otc.ingest",  # References the registered pipeline!
            ),
            
            # Lambda step: lightweight validation of ingest result
            Step.lambda_(
                name="validate_ingest",
                handler=validate_ingest_result,
                config={"min_records": 100},
            ),
            
            # Pipeline step: actual work done by OTCNormalizePipeline
            Step.pipeline(
                name="normalize",
                pipeline_name="otc.normalize",
            ),
            
            # Lambda step: check reject rate
            Step.lambda_(
                name="validate_normalize",
                handler=validate_normalize_result,
                config={"max_reject_rate": 0.05},
            ),
            
            # Pipeline step: compute summaries
            Step.pipeline(
                name="summarize",
                pipeline_name="otc.summarize",
            ),
            
            # Pipeline step: run quality checks
            Step.pipeline(
                name="quality_check",
                pipeline_name="otc.quality_check",
            ),
            
            # Lambda step: final quality gate
            Step.lambda_(
                name="quality_gate",
                handler=check_quality_grade,
                config={"min_grade": "C"},
            ),
        ],
        tags=["weekly", "otc", "finra"],
    )


# =============================================================================
# Step 4: Execute the Workflow
# =============================================================================

def run_otc_workflow(file_path: str, week_ending: str) -> None:
    """
    Run the OTC weekly workflow.
    
    Args:
        file_path: Path to FINRA PSV file
        week_ending: Week ending date (YYYY-MM-DD)
    """
    # Create workflow
    workflow = create_otc_weekly_workflow()
    
    # Create runner
    runner = WorkflowRunner()
    
    # Execute with parameters
    # These params are passed to all pipeline steps
    result = runner.execute(
        workflow,
        params={
            "file_path": file_path,
            "week_ending": week_ending,
        },
    )
    
    # Report results
    print(f"\n{'='*60}")
    print(f"Workflow: {result.workflow_name}")
    print(f"Status: {result.status.value}")
    print(f"Duration: {result.duration_seconds:.2f}s" if result.duration_seconds else "")
    print(f"Completed Steps: {len(result.completed_steps)}/{result.total_steps}")
    
    if result.error:
        print(f"\nError at '{result.error_step}': {result.error}")
    
    print(f"\nStep Results:")
    for step in result.step_executions:
        status_icon = "✓" if step.status == "completed" else "✗"
        print(f"  {status_icon} {step.step_name}: {step.status}")
        if step.result and step.result.output:
            for k, v in step.result.output.items():
                print(f"      {k}: {v}")


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    print("OTC Workflow Example")
    print("=" * 60)
    print()
    print("Key Architecture Points:")
    print("  1. Pipelines (OTCIngestPipeline, etc.) do the ACTUAL WORK")
    print("  2. Workflow orchestrates pipelines via Step.pipeline()")
    print("  3. Lambda steps do LIGHTWEIGHT validation only")
    print("  4. Don't copy pipeline logic into workflows!")
    print()
    print("Workflow Structure:")
    
    workflow = create_otc_weekly_workflow()
    for i, step in enumerate(workflow.steps, 1):
        step_type = step.step_type.value
        if step_type == "pipeline":
            print(f"  {i}. [{step_type}] {step.name} → {step.pipeline_name}")
        else:
            print(f"  {i}. [{step_type}] {step.name}")
    
    print()
    print("To run: python -m examples.otc_workflow")
    print()
    print("NOTE: Requires database connection and registered pipelines.")
    print("      For demo, see examples/finra_complete_demo.py which uses mocks.")
