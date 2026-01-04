"""
Spine Framework - Application infrastructure for data pipelines.

This module provides:
- Pipeline base classes and registration
- Structured logging with context
- Execution dispatching
- Pipeline runner

All components are tier-agnostic and work with any backend.
"""

from spine.framework.pipelines import Pipeline, PipelineResult, PipelineStatus
from spine.framework.registry import clear_registry, get_pipeline, list_pipelines, register_pipeline
from spine.framework.runner import PipelineRunner, get_runner

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
