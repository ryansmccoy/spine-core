#!/usr/bin/env python3
"""Framework Logging — Structured logging with context and timing.

WHY FRAMEWORK-LEVEL LOGGING
───────────────────────────
The observability module (06_observability) provides general logging.
The framework module adds *pipeline and workflow-aware* utilities:
• LogContext with execution_id, pipeline, domain, step fields.
• log_step() context manager that auto-measures duration.
• @log_timing decorator for function-level timing.

These fields align with the Workflow engine's own context.  When a
Workflow runs step "ingest", the framework logging context is set
automatically so every log line from the step carries the execution_id,
pipeline, and step name without any manual wiring.

ARCHITECTURE
────────────
    WorkflowRunner                     Framework Logging
    ──────────────                     ─────────────────
    execute(workflow, params)   ──▶    set_context(execution_id, pipeline)
      step "ingest"             ──▶      set_context(step="ingest")
        pipeline.run()                     with log_step("fetch"):
                                              ...work...
      step "transform"          ──▶      set_context(step="transform")
        pipeline.run()                     with log_step("normalise"):
                                              ...work...

    All log lines automatically include execution_id, pipeline,
    domain, and step — no manual threading required.

    @log_timing("validate_data")
    def validate_data(records): ...
         │
         ▼
    duration logged on each call

CONTEXT FIELDS
──────────────
    Field          Purpose
    ────────────── ────────────────────────────────
    execution_id   Links logs to a specific run
    pipeline       Which pipeline / workflow is running
    domain         Business domain (filings, otc)
    step           Current pipeline / workflow step
    capture_id     Arbitrary extra field (via bind)

Run: python examples/08_framework/07_framework_logging.py

Note: Requires structlog. Gracefully skips if not installed.

See Also:
    06_observability/01_structured_logging — general logging
    06_observability/03_context_binding — general context
    04_orchestration/03_workflow_context — workflow-level context
"""

import sys

try:
    import structlog
    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False


def main():
    if not HAS_STRUCTLOG:
        print("=" * 60)
        print("Framework Logging (SKIPPED - structlog not installed)")
        print("=" * 60)
        print("  Install with: pip install structlog")
        return

    from spine.framework.logging import (
        configure_logging,
    )
    from spine.framework.logging.context import (
        bind_context,
        clear_context,
        get_context,
        set_context,
    )
    from spine.framework.logging.timing import log_step, log_timing

    print("=" * 60)
    print("Framework Logging")
    print("=" * 60)

    # ── 1. Configure structured logging ─────────────────────────
    print("\n--- 1. Configure logging ---")
    configure_logging(level="DEBUG", format="console")
    logger = structlog.get_logger("example")
    logger.info("Logging configured", format="console", level="DEBUG")

    # ── 2. Context propagation ──────────────────────────────────
    print("\n--- 2. Log context ---")
    set_context(
        execution_id="exec_001",
        workflow="sec_ingest",
        domain="filings",
        step="fetch",
    )
    current = get_context()
    print(f"  execution_id: {current.execution_id}")
    print(f"  workflow:     {current.workflow}")
    print(f"  domain:       {current.domain}")
    print(f"  step:         {current.step}")

    # Bind additional context
    bind_context(capture_id="cap_abc123")
    current = get_context()
    print(f"  capture_id:   {current.capture_id}")

    # ── 3. Step timing ──────────────────────────────────────────
    print("\n--- 3. Step timing (log_step) ---")
    with log_step("fetch_filing") as timing:
        # Simulate work
        total = sum(range(100_000))
    print(f"  Step:     {timing.step}")
    print(f"  Duration: {timing.duration_ms:.1f}ms")

    with log_step("parse_sections") as timing:
        data = [i * 2 for i in range(50_000)]
    print(f"  Step:     {timing.step}")
    print(f"  Duration: {timing.duration_ms:.1f}ms")

    # ── 4. Function timing decorator ────────────────────────────
    print("\n--- 4. Function timing (log_timing) ---")

    @log_timing("validate_data")
    def validate_data(records: int) -> bool:
        """Simulate validation work."""
        _ = [i ** 2 for i in range(records)]
        return True

    result = validate_data(10_000)
    print(f"  Result: {result}")

    # ── 5. Clean up context ─────────────────────────────────────
    print("\n--- 5. Clear context ---")
    clear_context()
    ctx = get_context()
    print(f"  After clear - execution_id: {ctx.execution_id}")

    print("\n" + "=" * 60)
    print("[OK] Framework logging example complete")


if __name__ == "__main__":
    main()
