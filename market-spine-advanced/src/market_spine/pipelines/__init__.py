"""Pipelines layer - Composable data processing pipelines."""

from market_spine.pipelines.base import Pipeline, Step, StepResult, PipelineResult
from market_spine.pipelines.registry import PipelineRegistry
from market_spine.pipelines.runner import PipelineRunner

# Domain pipelines are auto-discovered from domains/

__all__ = [
    "Pipeline",
    "Step",
    "StepResult",
    "PipelineResult",
    "PipelineRegistry",
    "PipelineRunner",
]
