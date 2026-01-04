"""Pipeline registry - central registration of all pipelines."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class PipelineDefinition:
    """Definition of a registered pipeline."""

    name: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    description: str = ""
    requires_lock: bool = False
    lock_key_template: str | None = None


class PipelineRegistry:
    """Registry of all available pipelines."""

    def __init__(self):
        """Initialize empty registry."""
        self._pipelines: dict[str, PipelineDefinition] = {}

    def register(
        self,
        name: str,
        handler: Callable[[dict[str, Any]], dict[str, Any]],
        description: str = "",
        requires_lock: bool = False,
        lock_key_template: str | None = None,
    ) -> None:
        """Register a pipeline."""
        self._pipelines[name] = PipelineDefinition(
            name=name,
            handler=handler,
            description=description,
            requires_lock=requires_lock,
            lock_key_template=lock_key_template,
        )

    def get(self, name: str) -> PipelineDefinition | None:
        """Get a pipeline by name."""
        return self._pipelines.get(name)

    def list_pipelines(self) -> list[str]:
        """List all registered pipeline names."""
        return list(self._pipelines.keys())

    def all_definitions(self) -> list[PipelineDefinition]:
        """Get all pipeline definitions."""
        return list(self._pipelines.values())


# Global registry instance
_registry: PipelineRegistry | None = None


def get_registry() -> PipelineRegistry:
    """Get the global pipeline registry."""
    global _registry
    if _registry is None:
        _registry = PipelineRegistry()
        # Register OTC pipelines
        _register_otc_pipelines(_registry)
    return _registry


def _register_otc_pipelines(registry: PipelineRegistry) -> None:
    """Register OTC-related pipelines."""
    from market_spine.pipelines.otc import (
        otc_ingest,
        otc_normalize,
        otc_compute_daily_metrics,
        otc_full_etl,
        otc_backfill_range,
    )

    registry.register(
        name="otc_ingest",
        handler=otc_ingest,
        description="Ingest OTC trades from data source into raw table",
    )

    registry.register(
        name="otc_normalize",
        handler=otc_normalize,
        description="Normalize raw OTC trades into structured format",
    )

    registry.register(
        name="otc_compute_daily_metrics",
        handler=otc_compute_daily_metrics,
        description="Compute daily aggregate metrics from normalized trades",
    )

    registry.register(
        name="otc_full_etl",
        handler=otc_full_etl,
        description="Run full ETL: ingest → normalize → compute",
    )

    registry.register(
        name="otc_backfill_range",
        handler=otc_backfill_range,
        description="Backfill OTC data for a date range",
        requires_lock=True,
        lock_key_template="otc_backfill:{start_date}:{end_date}",
    )
