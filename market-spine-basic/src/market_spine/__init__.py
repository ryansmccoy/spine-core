"""
Market Spine Basic - CLI analytics pipeline system.

This is a thin application layer that:
- Provides CLI commands (spine db init, spine run, etc.)
- Configures SQLite as the storage backend
- Wires up the spine.framework components

All reusable code lives in:
- spine.core: Platform primitives
- spine.framework: Application framework
- spine.domains.*: Domain logic
"""

__version__ = "0.1.0"

# Re-export commonly used items for backwards compatibility
from spine.framework.dispatcher import Dispatcher, Lane, TriggerSource
from spine.framework.logging import configure_logging, get_logger
from spine.framework.pipelines import Pipeline, PipelineResult, PipelineStatus
from spine.framework.registry import get_pipeline, list_pipelines, register_pipeline

__all__ = [
    "Dispatcher",
    "Lane",
    "Pipeline",
    "PipelineResult",
    "PipelineStatus",
    "TriggerSource",
    "__version__",
    "configure_logging",
    "get_logger",
    "get_pipeline",
    "list_pipelines",
    "register_pipeline",
]
