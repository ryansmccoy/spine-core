"""Orchestration table models (01_orchestration.sql).

.. deprecated:: 0.5.0
    This module contains orphaned models. The backing SQL schema
    (01_orchestration.sql) was never implemented. These models are
    retained for potential future use but should not be relied upon.
    Use :mod:`spine.core.models.workflow` for workflow orchestration.

Models for pipeline group orchestration: group definitions,
run history, and step-to-execution mapping.
"""

from __future__ import annotations

import warnings

from dataclasses import dataclass


def _warn_deprecated(cls_name: str) -> None:
    warnings.warn(
        f"{cls_name} is deprecated: no backing SQL table exists. "
        "Use workflow models instead.",
        DeprecationWarning,
        stacklevel=3,
    )


# ---------------------------------------------------------------------------
# core_pipeline_groups  (DEPRECATED - no backing table)
# ---------------------------------------------------------------------------


@dataclass
class PipelineGroupRecord:
    """Pipeline group definition row (``core_pipeline_groups``).

    .. deprecated:: 0.5.0
        No backing SQL table exists. Use workflow models instead.
    """

    def __post_init__(self):
        _warn_deprecated("PipelineGroupRecord")

    id: str = ""
    name: str = ""
    domain: str = ""
    version: int = 1
    description: str | None = None
    spec: str = ""  # JSON: full group spec (steps, policy, defaults)
    tags: str | None = None  # JSON array of tags
    created_at: str = ""
    updated_at: str = ""
    created_by: str | None = None
    is_active: int = 1


# ---------------------------------------------------------------------------
# core_group_runs  (DEPRECATED - no backing table)
# ---------------------------------------------------------------------------


@dataclass
class GroupRun:
    """Group execution history row (``core_group_runs``).

    .. deprecated:: 0.5.0
        No backing SQL table exists. Use WorkflowRun instead.
    """

    def __post_init__(self):
        _warn_deprecated("GroupRun")

    id: str = ""
    group_name: str = ""
    group_version: int = 0
    params: str | None = None  # JSON runtime parameters
    status: str = "pending"  # pending, running, completed, failed, partial, cancelled
    trigger_source: str = "cli"  # cli, api, scheduler
    batch_id: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    created_at: str = ""


# ---------------------------------------------------------------------------
# core_group_run_steps  (DEPRECATED - no backing table)
# ---------------------------------------------------------------------------


@dataclass
class GroupRunStep:
    """Step-to-execution mapping within a group run (``core_group_run_steps``).

    .. deprecated:: 0.5.0
        No backing SQL table exists. Use WorkflowStep instead.
    """

    def __post_init__(self):
        _warn_deprecated("GroupRunStep")

    id: str = ""
    group_run_id: str = ""
    step_name: str = ""
    pipeline_name: str = ""
    execution_id: str | None = None
    sequence_order: int = 0
    status: str = "pending"  # pending, running, completed, failed, skipped
    params: str | None = None  # JSON merged parameters
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
