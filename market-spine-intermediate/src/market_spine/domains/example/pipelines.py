"""Example domain pipelines - demonstrates async pipelines for intermediate tier."""

from typing import Any

from market_spine.pipelines.base import Pipeline


class ExampleHelloPipeline(Pipeline):
    """Simple hello world pipeline for testing."""

    name = "example.hello"
    description = "A simple hello world pipeline for testing the framework"

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the pipeline."""
        name = params.get("name", "World")
        message = f"Hello, {name}!"

        return {"message": message, "name_length": len(name)}


class ExampleCountPipeline(Pipeline):
    """Pipeline that counts to a number."""

    name = "example.count"
    description = "Counts from 1 to N"

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the pipeline."""
        n = int(params.get("n", 10))
        total = sum(range(1, n + 1))

        return {"n": n, "total": total}


class ExampleFailPipeline(Pipeline):
    """Pipeline that always fails - for testing error handling."""

    name = "example.fail"
    description = "Always fails with an error"

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the pipeline."""
        raise RuntimeError("Intentional failure for testing")


# Register pipelines - intermediate uses class-based registry
def register_example_pipelines(registry):
    """Register example pipelines with the registry."""
    registry.register(ExampleHelloPipeline)
    registry.register(ExampleCountPipeline)
    registry.register(ExampleFailPipeline)
