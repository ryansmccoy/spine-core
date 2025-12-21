"""
Examples router — browse, inspect, and run spine-core examples.

Provides read access to the auto-discovered example registry and
run results produced by ``examples/run_all.py``.  Supports triggering
example runs as background processes.

Endpoints:
    GET  /examples                    List all discovered examples
    GET  /examples/categories         List category names
    GET  /examples/results            Summary + per-example results from last run
    GET  /examples/{name:path}/source Get source code for a specific example
    POST /examples/run                Trigger an example run (background)

Manifesto:
    Built-in example endpoints let new users explore the API
    interactively without setting up real data sources first.

Tags:
    spine-core, api, examples, onboarding, demo

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from spine.api.schemas.common import PagedResponse, PageMeta, SuccessResponse
from spine.api.schemas.examples import (
    ExampleRunResultSchema,
    ExampleSchema,
    ExamplesSummarySchema,
    RunExamplesRequest,
    RunExamplesResponse,
)

router = APIRouter(prefix="/examples")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _examples_root() -> Path:
    """Resolve the ``examples/`` directory relative to spine-core root."""
    # This file lives at src/spine/api/routers/examples.py
    # spine-core root is 4 levels up
    candidate = Path(__file__).resolve().parents[4] / "examples"
    if candidate.is_dir():
        return candidate
    # Fallback: check common Docker/CI locations
    for fallback in [Path("/app/examples"), Path.cwd() / "examples"]:
        if fallback.is_dir():
            return fallback
    return candidate  # return even if missing — callers handle gracefully


def _results_path() -> Path:
    """Path to ``examples/results/run_results.json``."""
    return _examples_root() / "results" / "run_results.json"


def _get_registry() -> Any:
    """Lazy-load the ExampleRegistry using importlib (no sys.path hacks).

    Uses importlib.util.spec_from_file_location to load _registry.py
    directly from the examples/ directory, avoiding module name conflicts.
    """
    root = _examples_root()
    registry_file = root / "_registry.py"

    if not registry_file.exists():
        logger.warning("Example registry not found at %s", registry_file)
        return None

    try:
        spec = importlib.util.spec_from_file_location(
            "examples._registry", str(registry_file)
        )
        if spec is None or spec.loader is None:
            logger.warning("Could not create module spec for %s", registry_file)
            return None

        module = importlib.util.module_from_spec(spec)
        # Register in sys.modules so @dataclass(slots=True) can resolve __module__
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        registry = module.ExampleRegistry(root=root)
        logger.info(
            "Loaded ExampleRegistry: %d examples in %d categories",
            len(registry), len(registry.categories),
        )
        return registry
    except Exception:
        logger.exception("Failed to load ExampleRegistry from %s", registry_file)
        return None


def _load_results() -> dict[str, Any] | None:
    """Load and return run_results.json, or None if missing."""
    path = _results_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _file_mtime_iso(path: Path) -> str | None:
    """Return the file modification time as an ISO string."""
    try:
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=UTC).isoformat()
    except Exception:
        return None


# Track running processes to prevent concurrent runs
_running_process: asyncio.subprocess.Process | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PagedResponse[ExampleSchema])
def list_examples(
    category: str | None = Query(None, description="Filter by category name"),
    limit: int = Query(200, ge=1, le=1000, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List all discovered examples from the filesystem registry.

    Scans numbered subdirectories under ``examples/`` and extracts
    metadata from module docstrings.  No examples are executed.

    Args:
        category: Optional filter by category (e.g. ``01_core``).
        limit: Maximum items per page (default 200, max 1000).
        offset: Pagination offset.

    Returns:
        PagedResponse with ExampleSchema items.
    """
    registry = _get_registry()
    if registry is None:
        return PagedResponse(
            data=[],
            page=PageMeta(total=0, limit=limit, offset=offset, has_more=False),
        )

    if category:
        all_examples = registry.by_category(category)
    else:
        all_examples = list(registry.examples)

    total = len(all_examples)
    page = all_examples[offset : offset + limit]

    items = [
        ExampleSchema(
            category=ex.category,
            name=ex.name,
            title=ex.title,
            description=ex.description,
            order=ex.order,
        )
        for ex in page
    ]

    return PagedResponse(
        data=items,
        page=PageMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        ),
    )


@router.get("/categories", response_model=SuccessResponse[list[str]])
def list_categories():
    """Return all category names from the example registry.

    Categories are derived from numbered subdirectories (e.g. ``01_core``,
    ``02_execution``).
    """
    registry = _get_registry()
    categories = registry.categories if registry else []
    return SuccessResponse(data=categories)


@router.get("/results", response_model=SuccessResponse[ExamplesSummarySchema])
def get_results():
    """Return the summary and per-example results from the last run.

    Reads from ``examples/results/run_results.json`` produced by
    ``run_all.py``.  Returns empty summary if no results exist yet.
    """
    results = _load_results()
    registry = _get_registry()
    categories = registry.categories if registry else []

    if results is None:
        total = len(registry) if registry else 0
        return SuccessResponse(
            data=ExamplesSummarySchema(
                total=total,
                passed=0,
                failed=0,
                categories=categories,
                last_run_at=None,
                examples=[],
            ),
        )

    example_results = [
        ExampleRunResultSchema(**ex) for ex in results.get("examples", [])
    ]

    last_run_at = _file_mtime_iso(_results_path())

    return SuccessResponse(
        data=ExamplesSummarySchema(
            total=results.get("total", 0),
            passed=results.get("passed", 0),
            failed=results.get("failed", 0),
            categories=categories,
            last_run_at=last_run_at,
            examples=example_results,
        ),
    )


@router.get("/{name:path}/source")
def get_example_source(name: str):
    """Return the Python source code for a specific example.

    Args:
        name: Example name in ``category/script`` format
              (e.g. ``01_core/01_basic_task``).

    Returns:
        JSON with ``source``, ``path``, ``line_count``, and ``language`` fields.
    """
    registry = _get_registry()
    if registry is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "Example registry not available"},
        )

    # Find the example by name
    example = None
    for ex in registry.examples:
        if ex.name == name:
            example = ex
            break

    if example is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Example '{name}' not found"},
        )

    source_path = example.path
    if not source_path.exists():
        return JSONResponse(
            status_code=404,
            content={"detail": f"Source file not found at {source_path}"},
        )

    try:
        source_code = source_path.read_text(encoding="utf-8")
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to read source: {exc}"},
        )

    return SuccessResponse(
        data={
            "name": name,
            "title": example.title,
            "description": example.description,
            "source": source_code,
            "path": str(source_path.relative_to(_examples_root())),
            "line_count": source_code.count("\n") + 1,
            "language": "python",
        },
    )


@router.post("/run", status_code=202)
async def run_examples(body: RunExamplesRequest | None = None):
    """Trigger an example run as a background subprocess.

    Spawns ``python examples/run_all.py`` in the background.  Returns
    202 Accepted immediately.  Poll ``GET /examples/results`` to check
    progress (the JSON file is written atomically on completion).

    Only one run is allowed at a time — subsequent requests while a run
    is active return a 409 Conflict.
    """
    global _running_process

    # Check if a run is already in progress
    if _running_process is not None and _running_process.returncode is None:
        return JSONResponse(
            status_code=409,
            content=RunExamplesResponse(
                status="already_running",
                message="An example run is already in progress.",
                pid=_running_process.pid,
            ).model_dump(),
        )

    root = _examples_root()
    run_script = root / "run_all.py"

    if not run_script.exists():
        return JSONResponse(
            status_code=404,
            content=RunExamplesResponse(
                status="error",
                message=f"run_all.py not found at {run_script}",
                pid=None,
            ).model_dump(),
        )

    cmd = [sys.executable, str(run_script)]
    if body and body.category:
        cmd.extend(["--category", body.category])
    if body and body.timeout:
        cmd.extend(["--timeout", str(body.timeout)])

    # Set environment for persistent recording
    import os

    env = {**os.environ}
    env.setdefault("SPINE_EXAMPLES_DB", "file")
    env.setdefault("SPINE_EXAMPLES_ORM_DB", "file")
    env.setdefault("SPINE_EXAMPLES_TAG", "1")

    _running_process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(root),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    return JSONResponse(
        status_code=202,
        content=RunExamplesResponse(
            status="started",
            message=f"Example run started (category={body.category if body else 'all'})",
            pid=_running_process.pid,
        ).model_dump(),
    )


@router.get("/run/status", response_model=SuccessResponse[RunExamplesResponse])
async def run_status():
    """Check whether an example run is currently in progress."""
    global _running_process

    if _running_process is None:
        return SuccessResponse(
            data=RunExamplesResponse(
                status="idle",
                message="No run in progress.",
                pid=None,
            ),
        )

    if _running_process.returncode is None:
        return SuccessResponse(
            data=RunExamplesResponse(
                status="running",
                message="Example run is in progress.",
                pid=_running_process.pid,
            ),
        )

    return SuccessResponse(
        data=RunExamplesResponse(
            status="completed" if _running_process.returncode == 0 else "failed",
            message=f"Last run exited with code {_running_process.returncode}.",
            pid=_running_process.pid,
        ),
    )
