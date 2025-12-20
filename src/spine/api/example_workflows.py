"""
Example workflow definitions auto-registered on API startup.

These provide real-looking workflows for the frontend dashboard,
and demonstrate the v2 Workflow DSL for spine-core consumers.
"""

from __future__ import annotations

from spine.core.logging import get_logger

from spine.orchestration.step_types import Step
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_registry import register_workflow

logger = get_logger(__name__)

_REGISTERED = False


def register_example_workflows() -> int:
    """Register built-in example workflows if they aren't already loaded.

    Returns the number of workflows registered (0 if already loaded).
    """
    global _REGISTERED  # noqa: PLW0603
    if _REGISTERED:
        return 0

    examples = [
        Workflow(
            name="etl.daily_ingest",
            domain="core",
            description="Daily data ingestion pipeline — extract, transform, load",
            steps=[
                Step.pipeline("extract", "core.extract"),
                Step.pipeline("validate", "core.validate", depends_on=["extract"]),
                Step.pipeline("transform", "core.transform", depends_on=["validate"]),
                Step.pipeline("load", "core.load", depends_on=["transform"]),
            ],
            tags=["etl", "daily"],
        ),
        Workflow(
            name="quality.full_scan",
            domain="quality",
            description="Run all quality checks across loaded datasets",
            steps=[
                Step.pipeline("schema_check", "quality.schema"),
                Step.pipeline("completeness", "quality.completeness"),
                Step.pipeline("business_rules", "quality.rules", depends_on=["schema_check", "completeness"]),
                Step.pipeline("report", "quality.report", depends_on=["business_rules"]),
            ],
            tags=["quality", "audit"],
        ),
        Workflow(
            name="reporting.weekly_summary",
            domain="reporting",
            description="Generate weekly summary reports and dashboards",
            steps=[
                Step.pipeline("aggregate", "reporting.aggregate"),
                Step.pipeline("render", "reporting.render", depends_on=["aggregate"]),
                Step.pipeline("distribute", "reporting.distribute", depends_on=["render"]),
            ],
            tags=["reporting", "weekly"],
        ),
    ]

    count = 0
    for workflow in examples:
        try:
            register_workflow(workflow)
            count += 1
        except ValueError:
            # Already registered (e.g. from test code)
            pass

    _REGISTERED = True
    logger.info("example_workflows_registered", count=count)
    return count
