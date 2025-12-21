"""WorkflowContext — Data passing between steps.

WHY IMMUTABLE CONTEXT
─────────────────────
When multiple steps share a mutable dict, one step can silently
corrupt another’s input.  Debugging which step mutated what is
nightmarish.  WorkflowContext is *immutable* — each with_output()
call returns a *new* context, leaving the original unchanged.
This makes data flow explicit and thread-safe.

DATA FLOW
─────────
    WorkflowContext.create(params, partition, batch_id)
         │
         ▼
    Step 1: ctx.params → compute → StepResult(output={...})
         │
    ctx2 = ctx.with_output("step1", output)
         │
         ▼
    Step 2: ctx2.get_output("step1", "field") → compute
         │
    ctx3 = ctx2.with_output("step2", output)
         │
         ▼
    Step 3: ctx3.get_output("step1", ...) + ctx3.get_output("step2", ...)

    Each ctx is a SEPARATE object.  The original ctx has NO outputs.

CONTEXT ATTRIBUTES
──────────────────
    Attribute       Type      Purpose
    ─────────────── ───────── ──────────────────────────────
    run_id          str       Unique workflow execution ID
    workflow_name   str       Workflow identifier
    params          dict      Immutable initial parameters
    partition       dict      Partition keys for idempotency
    outputs         dict      {step_name: {key: value, ...}}
    execution       obj       batch_id, execution_id, dry_run

BEST PRACTICES
──────────────
• Use get_output(step, key, default=...) for safe access.
• Never mutate ctx.params or ctx.outputs directly.
• Include partition keys for re-run idempotency.
• Pass batch_id for cross-workflow correlation.

Run: python examples/04_orchestration/03_workflow_context.py

See Also:
    08_tracked_runner — context in database-backed workflows
    15_runnable_protocol — how context flows through runnables
"""

from spine.execution.runnable import OperationRunResult
from spine.orchestration import (
    WorkflowContext,
    Workflow,
    Step,
    StepResult,
    WorkflowRunner,
)


class _NoOpRunnable:
    """Minimal Runnable for examples that only use lambda steps."""

    def submit_operation_sync(self, operation_name, params=None, *, parent_run_id=None, correlation_id=None):
        return OperationRunResult(status="completed")


def main():
    """Demonstrate WorkflowContext for step-to-step data passing."""
    print("=" * 60)
    print("WorkflowContext - Step-to-Step Data Passing")
    print("=" * 60)
    
    print("\n1. Creating a WorkflowContext...")
    
    # Create context with initial parameters
    ctx = WorkflowContext.create(
        workflow_name="data.operation",
        params={
            "source": "api",
            "tier": "NMS_TIER_1",
            "week_ending": "2025-12-26",
        },
        partition={"tier": "NMS_TIER_1", "week_ending": "2025-12-26"},
        batch_id="batch-12345",
        dry_run=False,
    )
    
    print(f"   Run ID: {ctx.run_id[:8]}...")
    print(f"   Workflow: {ctx.workflow_name}")
    print(f"   Params: {ctx.params}")
    print(f"   Partition: {ctx.partition}")
    
    print("\n2. Accessing context data...")
    
    # Get params
    tier = ctx.params.get("tier")
    print(f"   Tier from params: {tier}")
    
    # Get execution context (for lineage)
    print(f"   Batch ID: {ctx.execution.batch_id}")
    print(f"   Execution ID: {ctx.execution.execution_id[:8]}...")
    
    print("\n3. Step outputs and data flow...")
    
    # Simulate step outputs being added
    ctx_with_outputs = ctx.with_output("ingest", {
        "record_count": 1000,
        "source_file": "data.csv",
    })
    
    ctx_with_more = ctx_with_outputs.with_output("validate", {
        "valid_count": 950,
        "rejected_count": 50,
    })
    
    # Get outputs from previous steps
    print("   Getting outputs from previous steps:")
    record_count = ctx_with_more.get_output("ingest", "record_count")
    valid_count = ctx_with_more.get_output("validate", "valid_count")
    print(f"     Ingest record_count: {record_count}")
    print(f"     Validate valid_count: {valid_count}")
    
    # Default values for missing outputs
    missing = ctx_with_more.get_output("nonexistent", "field", default=0)
    print(f"     Missing field (default 0): {missing}")
    
    print("\n4. Immutability demonstration...")
    
    # Original context is unchanged
    print(f"   Original outputs: {ctx.outputs}")
    print(f"   New context outputs: {ctx_with_more.outputs}")
    print(f"   Same object? {ctx is ctx_with_more}")
    
    print("\n5. Workflow with context passing...")
    
    def step_one(ctx: WorkflowContext, config: dict) -> StepResult:
        """First step - produces data."""
        return StepResult.ok(output={"count": 100, "status": "fetched"})
    
    def step_two(ctx: WorkflowContext, config: dict) -> StepResult:
        """Second step - uses data from step one."""
        count = ctx.get_output("fetch", "count", 0)
        print(f"      Step two received count: {count}")
        return StepResult.ok(output={"processed": count * 2})
    
    def step_three(ctx: WorkflowContext, config: dict) -> StepResult:
        """Third step - uses data from both previous steps."""
        original = ctx.get_output("fetch", "count", 0)
        processed = ctx.get_output("transform", "processed", 0)
        print(f"      Step three: original={original}, processed={processed}")
        return StepResult.ok(output={"ratio": processed / original if original else 0})
    
    workflow = Workflow(
        name="context.demo",
        steps=[
            Step.lambda_("fetch", step_one),
            Step.lambda_("transform", step_two),
            Step.lambda_("analyze", step_three),
        ],
    )
    
    runner = WorkflowRunner(runnable=_NoOpRunnable())
    result = runner.execute(workflow, params={"demo": True})
    
    print(f"\n   Final outputs:")
    for step_exec in result.step_executions:
        output = step_exec.result.output if step_exec.result else {}
        print(f"     {step_exec.step_name}: {output}")
    
    print("\n6. Context serialization...")
    
    # Context can be serialized for checkpointing
    ctx_dict = {
        "run_id": ctx.run_id,
        "workflow_name": ctx.workflow_name,
        "params": ctx.params,
        "partition": ctx.partition,
        "outputs": ctx.outputs,
    }
    
    print(f"   Serializable: {list(ctx_dict.keys())}")
    
    print("\n" + "=" * 60)
    print("WorkflowContext demo complete!")


if __name__ == "__main__":
    main()
