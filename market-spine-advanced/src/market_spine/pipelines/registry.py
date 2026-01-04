"""Pipeline registry - Central catalog of available pipelines."""

from typing import Type

import structlog

from market_spine.pipelines.base import Pipeline

logger = structlog.get_logger()


class PipelineRegistry:
    """
    Registry for pipeline definitions.

    Use the @PipelineRegistry.register decorator or .register_pipeline() method
    to add pipelines to the registry.
    """

    _pipelines: dict[str, Type[Pipeline]] = {}

    @classmethod
    def register(cls, pipeline_class: Type[Pipeline]) -> Type[Pipeline]:
        """
        Decorator to register a pipeline class.

        Usage:
            @PipelineRegistry.register
            class MyPipeline(Pipeline):
                name = "my_pipeline"
                ...
        """
        name = pipeline_class.name
        if name in cls._pipelines:
            logger.warning(
                "pipeline_overwritten",
                name=name,
                old=cls._pipelines[name].__name__,
                new=pipeline_class.__name__,
            )

        cls._pipelines[name] = pipeline_class
        logger.debug("pipeline_registered", name=name, class_name=pipeline_class.__name__)
        return pipeline_class

    @classmethod
    def register_pipeline(cls, pipeline_class: Type[Pipeline]) -> None:
        """Register a pipeline class (non-decorator version)."""
        cls.register(pipeline_class)

    @classmethod
    def get(cls, name: str) -> Type[Pipeline] | None:
        """Get a pipeline class by name."""
        return cls._pipelines.get(name)

    @classmethod
    def get_or_raise(cls, name: str) -> Type[Pipeline]:
        """Get a pipeline class by name, raising if not found."""
        pipeline = cls._pipelines.get(name)
        if pipeline is None:
            available = list(cls._pipelines.keys())
            raise ValueError(f"Pipeline '{name}' not found. Available: {available}")
        return pipeline

    @classmethod
    def list_pipelines(cls) -> list[dict]:
        """List all registered pipelines with metadata."""
        return [
            {
                "name": name,
                "class": p.__name__,
                "description": p.description,
            }
            for name, p in sorted(cls._pipelines.items())
        ]

    @classmethod
    def clear(cls) -> None:
        """Clear all registered pipelines (for testing)."""
        cls._pipelines.clear()

    @classmethod
    def count(cls) -> int:
        """Get the number of registered pipelines."""
        return len(cls._pipelines)
