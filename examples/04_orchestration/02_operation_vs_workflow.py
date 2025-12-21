#!/usr/bin/env python3
"""Operation vs Workflow — Understanding the differences.

WHY THIS DISTINCTION MATTERS
────────────────────────────
Choosing the wrong abstraction leads to either:
• Monolithic "god operations" that can't be reused, or
• Over-orchestrated workflows for simple transformations.
Spine separates the two so that operations stay composable and
workflows stay readable.

DECISION GUIDE
──────────────
    Question                     Answer         Use
    ──────────────────────────── ────────────── ────────────
    Does it transform data?      Yes            Operation
    Does it have branching?      Yes            Workflow
    Is it reusable across        Yes            Operation
      different contexts?
    Does it coordinate           Yes            Workflow
      multiple operations?

    → Workflows INVOKE Operations (they work together!)

ARCHITECTURE
────────────
    Operation (stateless transform):
    ┌─────────┐   ┌───────────┐   ┌──────┐
    │ Extract │─▶│ Transform │─▶│ Load │   (ETL)
    └─────────┘   └───────────┘   └──────┘

    Workflow (orchestration with control flow):
    ┌───────────┐       ┌─────────┐
    │ Check QA  │── ✓ ─▶│Validate │──▶ store()
    └─────┬─────┘       └─────────┘
          │  ✗
          └────────▶┌────────┐
                    │ Enrich │───▶ store()
                    └────────┘

KEY DIFFERENCE
──────────────
    Aspect          Operation                 Workflow
    ─────────────── ──────────────────────── ────────────────────────
    Purpose         Data transformation      Orchestration
    State           Stateless                Stateful (WorkflowContext)
    Branching       No                       Yes (if/else, choice)
    Reusability     High (composable)        Moderate (domain-specific)
    Tracking        RunRecord per step       Full workflow status

Run: python examples/04_orchestration/02_operation_vs_workflow.py

See Also:
    01_workflow_basics — basic sequential workflow
    05_choice_branching — conditional workflow logic
    docs/guides/operation_vs_workflow.md — detailed decision guide
"""
import asyncio
from spine.execution import EventDispatcher, HandlerRegistry
from spine.execution.executors import MemoryExecutor


# === Operation-style handlers (transform data) ===

async def operation_extract(params: dict) -> dict:
    """Extract raw data."""
    source = params.get("source", "default")
    return {
        "raw_data": [1, 2, 3, 4, 5],
        "source": source,
        "stage": "extracted",
    }


async def operation_transform(params: dict) -> dict:
    """Transform raw data."""
    raw = params.get("raw_data", [])
    return {
        "transformed_data": [x * 2 for x in raw],
        "source": params.get("source"),
        "stage": "transformed",
    }


async def operation_load(params: dict) -> dict:
    """Load transformed data."""
    data = params.get("transformed_data", [])
    return {
        "loaded_count": len(data),
        "destination": "warehouse",
        "stage": "loaded",
    }


# === Workflow-style handlers (branching logic) ===

async def workflow_check_data(params: dict) -> dict:
    """Check data quality and decide next action."""
    data = params.get("data", [])
    quality_score = len([x for x in data if x > 0]) / max(len(data), 1)
    
    return {
        "quality_score": quality_score,
        "needs_enrichment": quality_score < 0.8,
        "needs_validation": quality_score >= 0.8,
    }


async def workflow_enrich(params: dict) -> dict:
    """Enrich low-quality data."""
    data = params.get("data", [])
    return {
        "enriched_data": [max(x, 1) for x in data],
        "action": "enriched",
    }


async def workflow_validate(params: dict) -> dict:
    """Validate high-quality data."""
    data = params.get("data", [])
    return {
        "validated_data": data,
        "action": "validated",
    }


async def workflow_store(params: dict) -> dict:
    """Store processed data."""
    return {
        "stored": True,
        "action": params.get("action", "unknown"),
    }


async def main():
    print("=" * 60)
    print("Operation vs Workflow")
    print("=" * 60)
    
    # === Setup ===
    registry = HandlerRegistry()
    
    # Operation handlers
    registry.register("task", "extract", operation_extract)
    registry.register("task", "transform", operation_transform)
    registry.register("task", "load", operation_load)
    
    # Workflow handlers
    registry.register("task", "check_data", workflow_check_data)
    registry.register("task", "enrich", workflow_enrich)
    registry.register("task", "validate", workflow_validate)
    registry.register("task", "store", workflow_store)
    
    handlers = {
        "task:extract": operation_extract,
        "task:transform": operation_transform,
        "task:load": operation_load,
        "task:check_data": workflow_check_data,
        "task:enrich": workflow_enrich,
        "task:validate": workflow_validate,
        "task:store": workflow_store,
    }
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = EventDispatcher(executor=executor, registry=registry)
    
    # === Operation Pattern (ETL) ===
    print("\n[Operation] ETL Pattern")
    print("  Extract → Transform → Load (linear, no branching)")
    
    # Step 1: Extract
    r1 = await dispatcher.submit_task("extract", {"source": "api"})
    extracted = (await dispatcher.get_run(r1)).result
    print(f"  1. Extracted: {extracted['raw_data']} from {extracted['source']}")
    
    # Step 2: Transform (uses extract output)
    r2 = await dispatcher.submit_task("transform", extracted)
    transformed = (await dispatcher.get_run(r2)).result
    print(f"  2. Transformed: {transformed['transformed_data']}")
    
    # Step 3: Load (uses transform output)
    r3 = await dispatcher.submit_task("load", transformed)
    loaded = (await dispatcher.get_run(r3)).result
    print(f"  3. Loaded: {loaded['loaded_count']} items to {loaded['destination']}")
    
    # === Workflow Pattern (with branching) ===
    print("\n[Workflow] Conditional Processing")
    print("  Check → (Enrich OR Validate) → Store (branching)")
    
    async def process_with_workflow(data: list) -> dict:
        """Process data with conditional branching."""
        # Step 1: Check quality
        r1 = await dispatcher.submit_task("check_data", {"data": data})
        check = (await dispatcher.get_run(r1)).result
        
        print(f"  1. Quality check: score={check['quality_score']:.2f}")
        
        # Step 2: Branch based on quality
        if check["needs_enrichment"]:
            print("  2. Path: ENRICH (low quality)")
            r2 = await dispatcher.submit_task("enrich", {"data": data})
            processed = (await dispatcher.get_run(r2)).result
        else:
            print("  2. Path: VALIDATE (high quality)")
            r2 = await dispatcher.submit_task("validate", {"data": data})
            processed = (await dispatcher.get_run(r2)).result
        
        # Step 3: Store (common ending)
        r3 = await dispatcher.submit_task("store", {"action": processed["action"]})
        stored = (await dispatcher.get_run(r3)).result
        print(f"  3. Stored with action: {stored['action']}")
        
        return stored
    
    # Test with different data quality
    print("\n  --- Low quality data ---")
    await process_with_workflow([1, 0, -1, 0, 2])  # Some zeros/negatives
    
    print("\n  --- High quality data ---")
    await process_with_workflow([1, 2, 3, 4, 5])  # All positive
    
    # === Comparison ===
    print("\n[Comparison]")
    print("  Operation Characteristics:")
    print("    ✓ Linear flow: A → B → C")
    print("    ✓ Each step transforms data")
    print("    ✓ Predictable execution path")
    print("    ✓ Good for ETL, data processing")
    
    print("\n  Workflow Characteristics:")
    print("    ✓ Conditional branching")
    print("    ✓ Dynamic path selection")
    print("    ✓ Can have parallel branches")
    print("    ✓ Good for business processes, orchestration")
    
    print("\n" + "=" * 60)
    print("[OK] Operation vs Workflow Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
