#!/usr/bin/env python3
"""Parameter Validation — PipelineSpec with ParamDef.

WHY PARAMETER VALIDATION
────────────────────────
Pipelines and workflow steps accept user-supplied dicts, and bad values
cause crashes deep in business logic where the error message is
unhelpful.  Spine’s PipelineSpec validates inputs *before* execution and
produces clear, actionable error messages plus auto-generated help text.

This validation layer works the same whether you call a Pipeline
directly, run it via PipelineRunner, or wire it into a Workflow.
The Workflow engine calls validate_params() on each step before
execution, so defining a PipelineSpec is the single place to
enforce contracts across all invocation paths.

ARCHITECTURE
────────────
    PipelineSpec
    ┌─────────────────────────────────────┐
    │ required_params:                    │
    │   ticker:  ParamDef(str, ...)       │
    │   start_date: ParamDef(str, valid.) │
    │ optional_params:                    │
    │   limit: ParamDef(int, default=100) │
    └─────────────────┬───────────────────┘
                      │ spec.validate(params)
                      ▼
    ┌─────────────────────────────────────┐
    │ ValidationResult                    │
    │   .valid, .missing_params           │
    │   .invalid_params, .has_errors      │
    │   .get_error_message()              │
    └─────────────────────────────────────┘

    Used by:
      Pipeline.validate_params()   — direct call
      PipelineRunner.run()         — auto-validated
      WorkflowRunner.execute()     — each step validated
      ManagedWorkflow.run()        — validated before dispatch

BUILT-IN VALIDATORS
───────────────────
    Validator       Checks
    ─────────────── ────────────────────────────
    date_format     ISO 8601 date (YYYY-MM-DD)
    enum_value(E)   Value is a member of Enum E
    positive_int    int > 0
    file_exists     Path exists on filesystem

BEST PRACTICES
──────────────
• Define PipelineSpec as a class constant for reuse.
• Call spec.validate() before pipeline.run().
• Use spec.get_help_text() for CLI --help output.
• Set error_message on ParamDef for user-friendly errors.
• Works with both Pipeline classes and plain @workflow_step functions.

Run: python examples/08_framework/04_params_validation.py

See Also:
    01_pipeline_basics — Pipeline with validate_params()
    02_pipeline_runner — runner calls validation automatically
    04_orchestration/04_step_adapters — validated plain functions
"""

from datetime import date
from pathlib import Path

from spine.core.enums import EventType
from spine.framework.params import (
    ParamDef,
    PipelineSpec,
    date_format,
    enum_value,
    positive_int,
)


def main():
    print("=" * 60)
    print("Pipeline Parameter Validation")
    print("=" * 60)

    # ── 1. Define a PipelineSpec ────────────────────────────────
    print("\n--- 1. Define PipelineSpec ---")
    spec = PipelineSpec(
        required_params={
            "ticker": ParamDef(
                name="ticker",
                type=str,
                description="Stock ticker symbol (e.g. AAPL)",
            ),
            "start_date": ParamDef(
                name="start_date",
                type=str,
                description="Start date in ISO format (YYYY-MM-DD)",
                validator=date_format,
                error_message="Must be a valid ISO date (YYYY-MM-DD)",
            ),
            "event_type": ParamDef(
                name="event_type",
                type=str,
                description="Type of event to process",
                validator=enum_value(EventType),
                error_message=f"Must be one of: {', '.join(e.value for e in list(EventType)[:5])}...",
            ),
        },
        optional_params={
            "limit": ParamDef(
                name="limit",
                type=int,
                description="Max number of results",
                default=100,
                validator=positive_int,
                error_message="Must be a positive integer",
            ),
            "output_dir": ParamDef(
                name="output_dir",
                type=str,
                description="Output directory path",
                default="./output",
            ),
        },
        description="Process corporate events for a given ticker and date range.",
        examples=[
            'params = {"ticker": "AAPL", "start_date": "2025-01-01", "event_type": "earnings_release"}',
        ],
        notes=[
            "Dates must be in ISO 8601 format",
            "Event types correspond to spine.core.enums.EventType values",
        ],
    )
    print("  Spec created with 3 required + 2 optional params")

    # ── 2. Generate help text ───────────────────────────────────
    print("\n--- 2. Help text ---")
    print(spec.get_help_text())

    # ── 3. Validate good input ──────────────────────────────────
    print("--- 3. Validate good input ---")
    good_params = {
        "ticker": "AAPL",
        "start_date": "2025-01-15",
        "event_type": "earnings_release",
    }
    result = spec.validate(good_params)
    print(f"  Valid:    {result.valid}")
    print(f"  Errors:   {result.has_errors}")
    print(f"  Message:  {result.get_error_message()}")
    # Check that defaults were applied
    print(f"  limit:    {good_params.get('limit')} (default applied)")

    # ── 4. Validate bad input — missing required ────────────────
    print("\n--- 4. Missing required params ---")
    missing_params = {"ticker": "AAPL"}
    result = spec.validate(missing_params)
    print(f"  Valid:   {result.valid}")
    print(f"  Missing: {result.missing_params}")
    print(f"  Message: {result.get_error_message()}")

    # ── 5. Validate bad input — invalid values ──────────────────
    print("\n--- 5. Invalid values ---")
    bad_params = {
        "ticker": "AAPL",
        "start_date": "not-a-date",
        "event_type": "invalid_event",
        "limit": -5,
    }
    result = spec.validate(bad_params)
    print(f"  Valid:   {result.valid}")
    print(f"  Invalid: {result.invalid_params}")
    print(f"  Message: {result.get_error_message()}")

    # ── 6. Individual ParamDef validation ───────────────────────
    print("\n--- 6. ParamDef.validate() ---")
    date_param = ParamDef(
        name="date",
        type=str,
        description="A date",
        validator=date_format,
    )
    ok, err = date_param.validate("2025-06-15")
    print(f"  '2025-06-15': valid={ok}, error={err}")

    ok, err = date_param.validate("June 15th")
    print(f"  'June 15th':  valid={ok}, error={err}")

    # Also works with date objects
    ok, err = date_param.validate(date(2025, 6, 15))
    print(f"  date(2025,6,15): valid={ok}, error={err}")

    print("\n" + "=" * 60)
    print("[OK] Params validation example complete")


if __name__ == "__main__":
    main()
