"""Pipeline registry - Singleton registry of available pipelines."""

from typing import Type

import structlog

from market_spine.pipelines.base import Pipeline

logger = structlog.get_logger()


class PipelineRegistry:
    """
    Singleton registry for pipeline classes.

    Pipelines are registered by name and can be retrieved for execution.
    """

    _instance: "PipelineRegistry | None" = None
    _pipelines: dict[str, Type[Pipeline]]

    def __new__(cls) -> "PipelineRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pipelines = {}
        return cls._instance

    def register(self, pipeline_class: Type[Pipeline]) -> None:
        """Register a pipeline class."""
        name = pipeline_class.name
        if name in self._pipelines:
            logger.warning("pipeline_already_registered", name=name)
        self._pipelines[name] = pipeline_class
        logger.debug("pipeline_registered", name=name)

    def get(self, name: str) -> Pipeline | None:
        """Get a pipeline instance by name."""
        pipeline_class = self._pipelines.get(name)
        if pipeline_class:
            return pipeline_class()
        return None

    def list_pipelines(self) -> list[dict[str, str]]:
        """List all registered pipelines."""
        return [
            {"name": cls.name, "description": cls.description} for cls in self._pipelines.values()
        ]

    def clear(self) -> None:
        """Clear all registered pipelines (for testing)."""
        self._pipelines.clear()


# Global registry instance
registry = PipelineRegistry()


def register_default_pipelines() -> None:
    """
    Register all default pipelines.

    Pipelines are auto-discovered from the domains/ directory.
    Each domain module should define a register_*_pipelines function.
    """
    import importlib
    import pkgutil
    from pathlib import Path

    domains_path = Path(__file__).parent / "domains"
    if domains_path.exists():
        for _, name, is_pkg in pkgutil.iter_modules([str(domains_path)]):
            if not is_pkg:
                continue  # Only process packages (directories)
            try:
                module = importlib.import_module(f"market_spine.domains.{name}.pipelines")
                # Look for register function
                register_fn_name = f"register_{name}_pipelines"
                if hasattr(module, register_fn_name):
                    getattr(module, register_fn_name)(registry)
                    logger.debug("domain_pipelines_registered", domain=name)
            except ImportError as e:
                logger.debug("domain_pipelines_not_found", domain=name, error=str(e))

    logger.info("pipeline_discovery_complete", count=len(registry.list_pipelines()))


# Auto-register on import
register_default_pipelines()
