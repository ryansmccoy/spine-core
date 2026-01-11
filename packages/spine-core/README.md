# spine-core

Internal utilities for data pipeline orchestration.

## Installation

```bash
pip install spine-core
```

## Overview

This package provides common primitives for building data pipelines:

- `spine.core` — Workflow tracking, data quality checks, temporal utilities
- `spine.framework` — Pipeline base classes, execution dispatch, logging
- `spine.orchestration` — Pipeline grouping and dependency management

## Usage

```python
from spine.framework import Pipeline, PipelineResult, PipelineStatus
from spine.orchestration import PipelineGroup, PipelineStep

# Define a pipeline
class MyPipeline(Pipeline):
    name = "my.pipeline"
    
    def run(self):
        # pipeline logic here
        return PipelineResult(status=PipelineStatus.COMPLETED, ...)

# Group pipelines with dependencies
group = PipelineGroup(
    name="my.workflow",
    steps=[
        PipelineStep(name="extract", pipeline="my.extract"),
        PipelineStep(name="transform", pipeline="my.transform", depends_on=["extract"]),
    ]
)
```

## Development

```bash
uv sync
uv run pytest tests/ -v
```

## License

MIT
