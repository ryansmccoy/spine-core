"""Pipeline definitions and registry."""

from market_spine.pipelines.registry import PipelineRegistry, get_registry
from market_spine.pipelines.runner import run_pipeline

# Domain pipelines are auto-discovered from domains/

__all__ = [
    "PipelineRegistry",
    "get_registry",
    "run_pipeline",
]
