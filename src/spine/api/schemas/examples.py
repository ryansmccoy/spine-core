"""Pydantic schemas for the Examples API.

Mirrors the ``ExampleInfo`` dataclass from ``examples/_registry.py``
and the ``run_results.json`` output from ``examples/run_all.py``.

Manifesto:
    Example schemas for OpenAPI documentation give users copy-paste
    request bodies so they can start integrating faster.

Tags:
    spine-core, api, schemas, examples, openapi, documentation

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── Registry schemas (filesystem-discovered) ─────────────────────────


class ExampleSchema(BaseModel):
    """A single discovered example script."""

    category: str = Field(..., description="Category directory, e.g. '01_core'")
    name: str = Field(..., description="Relative name, e.g. '01_core/01_result_pattern'")
    title: str = Field("", description="First line of module docstring")
    description: str = Field("", description="Full module docstring")
    order: int = Field(0, description="Numeric prefix for sorting")


# ── Run-result schemas (from run_results.json) ───────────────────────


class ExampleRunResultSchema(BaseModel):
    """Result of a single example execution."""

    name: str = Field(..., description="Example name, e.g. '01_core/01_result_pattern'")
    category: str = Field(..., description="Category directory")
    title: str = Field("", description="Example title")
    status: str = Field(..., description="'PASS' or 'FAIL'")
    duration_seconds: float = Field(0.0, description="Wall-clock execution time")
    stdout_tail: list[str] = Field(
        default_factory=list,
        description="Last N lines of stdout/stderr",
    )


class ExamplesSummarySchema(BaseModel):
    """Aggregate summary of the last example run."""

    total: int = Field(0, description="Total examples executed")
    passed: int = Field(0, description="Number that passed")
    failed: int = Field(0, description="Number that failed")
    categories: list[str] = Field(
        default_factory=list,
        description="All known category names",
    )
    last_run_at: str | None = Field(
        None,
        description="ISO timestamp of last run (file mtime)",
    )
    examples: list[ExampleRunResultSchema] = Field(
        default_factory=list,
        description="Per-example results from the last run",
    )


class RunExamplesRequest(BaseModel):
    """Request body for triggering an example run."""

    category: str | None = Field(
        None,
        description="Run only this category (e.g. '01_core'). Null = all.",
    )
    timeout: int = Field(
        120,
        ge=10,
        le=600,
        description="Per-example timeout in seconds",
    )


class RunExamplesResponse(BaseModel):
    """Response after triggering an example run."""

    status: str = Field(..., description="'started' or 'already_running'")
    message: str = Field(..., description="Human-readable status message")
    pid: int | None = Field(None, description="Process ID of the runner")
