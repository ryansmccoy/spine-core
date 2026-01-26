"""
Spine Framework - Application infrastructure for data pipelines.

This module provides:
- Pipeline base classes and registration
- Structured logging with context
- Execution dispatching
- Pipeline runner
- Source protocol and adapters (NEW)
- Alerting framework (NEW)

All components are tier-agnostic and work with any backend.
"""

from spine.framework.pipelines import Pipeline, PipelineResult, PipelineStatus
from spine.framework.registry import clear_registry, get_pipeline, list_pipelines, register_pipeline
from spine.framework.runner import PipelineRunner, get_runner

# New modules - imported lazily to avoid circular imports
# Use: from spine.framework.sources import FileSource, source_registry
# Use: from spine.framework.alerts import SlackChannel, alert_registry

__all__ = [
    # Pipelines
    "Pipeline",
    "PipelineResult",
    "PipelineStatus",
    # Registry
    "register_pipeline",
    "get_pipeline",
    "list_pipelines",
    "clear_registry",
    # Runner
    "PipelineRunner",
    "get_runner",
]
