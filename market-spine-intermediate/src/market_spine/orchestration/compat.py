"""
Compatibility layer for spine-core orchestration.

This module provides adapters that allow market-spine-intermediate's
pipeline pattern (execute(params)) to work with spine-core's 
orchestration module (Pipeline.run() with params in constructor).

The adapter wraps intermediate pipelines so they can be:
1. Registered with spine-core's registry
2. Executed by spine-core's GroupRunner
3. Orchestrated as PipelineGroups

Usage:
    from market_spine.orchestration.compat import adapt_pipeline
    from market_spine.domains.example.pipelines import ExampleHelloPipeline
    
    # Register adapted pipeline with spine-core
    AdaptedPipeline = adapt_pipeline(ExampleHelloPipeline)
    register_pipeline("example.hello")(AdaptedPipeline)
"""

from datetime import datetime
from typing import Any, Type

from spine.framework import Pipeline as SpineCorePipeline
from spine.framework import PipelineResult, PipelineStatus

from market_spine.pipelines.base import Pipeline as IntermediatePipeline


def adapt_pipeline(
    intermediate_cls: Type[IntermediatePipeline],
) -> Type[SpineCorePipeline]:
    """
    Adapt an intermediate-tier pipeline to spine-core's interface.
    
    Intermediate pattern:
        class MyPipeline(Pipeline):
            def execute(self, params: dict) -> dict:
                return {"result": "value"}
    
    Spine-core pattern:
        class MyPipeline(Pipeline):
            def run(self) -> PipelineResult:
                # self.params contains the params
                return PipelineResult(status=COMPLETED, ...)
    
    Args:
        intermediate_cls: An intermediate-tier Pipeline subclass
        
    Returns:
        A spine-core compatible Pipeline class
    """
    
    class AdaptedPipeline(SpineCorePipeline):
        """Adapted pipeline that wraps intermediate-tier execute() pattern."""
        
        name = intermediate_cls.name
        description = intermediate_cls.description
        
        def run(self) -> PipelineResult:
            """Execute the wrapped pipeline and convert result to PipelineResult."""
            started_at = datetime.now()
            
            # Create instance of intermediate pipeline
            intermediate_instance = intermediate_cls()
            
            try:
                # Call intermediate's execute(params) method
                result_dict = intermediate_instance.execute(self.params)
                
                return PipelineResult(
                    status=PipelineStatus.COMPLETED,
                    started_at=started_at,
                    completed_at=datetime.now(),
                    metrics=result_dict if isinstance(result_dict, dict) else {},
                )
                
            except Exception as e:
                return PipelineResult(
                    status=PipelineStatus.FAILED,
                    started_at=started_at,
                    completed_at=datetime.now(),
                    error=str(e),
                )
    
    # Preserve the original class name for debugging
    AdaptedPipeline.__name__ = f"Adapted{intermediate_cls.__name__}"
    AdaptedPipeline.__qualname__ = f"Adapted{intermediate_cls.__qualname__}"
    
    return AdaptedPipeline


def register_adapted_pipelines() -> None:
    """
    Register intermediate-tier pipelines with spine-core's registry.
    
    This makes all intermediate pipelines available for:
    - spine-core's GroupRunner orchestration
    - PipelineGroup execution
    - Cross-tier orchestration
    """
    from spine.framework import register_pipeline
    
    from market_spine.registry import registry
    
    # Get all pipelines from intermediate's registry
    for pipeline_info in registry.list_pipelines():
        name = pipeline_info["name"]
        intermediate_cls = registry._pipelines.get(name)
        
        if intermediate_cls:
            # Adapt and register with spine-core
            adapted_cls = adapt_pipeline(intermediate_cls)
            
            # Use try/except to handle already-registered pipelines
            try:
                register_pipeline(name)(adapted_cls)
            except ValueError:
                # Already registered (e.g., from spine-domains)
                pass
