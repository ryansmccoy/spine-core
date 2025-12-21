"""
Functions router — AWS Lambda-inspired function management and execution.

Create, edit, save, and execute Python functions from the browser.
Supports local subprocess execution and (future) container-based execution.

Endpoints:
    GET    /functions                      List all saved functions
    POST   /functions                      Create a new function
    GET    /functions/{function_id}        Get function details + source
    PUT    /functions/{function_id}        Update function source / config
    DELETE /functions/{function_id}        Delete a function
    POST   /functions/{function_id}/invoke Invoke (execute) a function
    GET    /functions/{function_id}/logs   Get execution logs
    GET    /functions/templates            List starter templates

Manifesto:
    Registered handler functions should be invocable and
    inspectable through the API for ad-hoc execution and debugging.

Tags:
    spine-core, api, functions, handlers, invocation

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from spine.api.schemas.common import PagedResponse, PageMeta, SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/functions")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class FunctionConfig(BaseModel):
    """Runtime configuration for a function."""
    timeout: int = Field(default=30, ge=1, le=300, description="Max execution time in seconds")
    memory_mb: int = Field(default=128, ge=64, le=1024, description="Memory limit in MB")
    runtime: str = Field(default="python3.12", description="Runtime identifier")
    env_vars: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    handler: str = Field(default="handler", description="Entry function name")


class FunctionCreate(BaseModel):
    """Request body for creating a new function."""
    name: str = Field(..., min_length=1, max_length=100, description="Function name")
    description: str = Field(default="", max_length=500)
    source: str = Field(default="", description="Python source code")
    config: FunctionConfig = Field(default_factory=FunctionConfig)
    tags: list[str] = Field(default_factory=list)


class FunctionUpdate(BaseModel):
    """Request body for updating a function."""
    name: str | None = None
    description: str | None = None
    source: str | None = None
    config: FunctionConfig | None = None
    tags: list[str] | None = None


class FunctionSummary(BaseModel):
    """Summary view of a function (list endpoint)."""
    id: str
    name: str
    description: str
    runtime: str
    handler: str
    timeout: int
    memory_mb: int
    tags: list[str]
    source_lines: int
    last_modified: str
    last_invoked: str | None
    invoke_count: int
    status: str  # "idle" | "running" | "error"


class FunctionDetail(BaseModel):
    """Full function detail including source code."""
    id: str
    name: str
    description: str
    source: str
    config: FunctionConfig
    tags: list[str]
    created_at: str
    last_modified: str
    last_invoked: str | None
    invoke_count: int
    status: str
    last_result: dict[str, Any] | None = None


class InvokeRequest(BaseModel):
    """Request body for invoking a function."""
    event: dict[str, Any] = Field(default_factory=dict, description="Event payload (like Lambda event)")
    context: dict[str, Any] = Field(default_factory=dict, description="Context overrides")
    timeout: int | None = Field(default=None, ge=1, le=300, description="Override timeout")
    dry_run: bool = Field(default=False, description="Validate without executing")


class InvokeResult(BaseModel):
    """Result of a function invocation."""
    request_id: str
    function_id: str
    function_name: str
    status: str  # "success" | "error" | "timeout"
    result: Any = None
    logs: str = ""
    error: str | None = None
    error_type: str | None = None
    duration_ms: float = 0
    billed_duration_ms: float = 0
    memory_used_mb: int | None = None
    started_at: str
    ended_at: str


class InvocationLog(BaseModel):
    """Log entry for a function invocation."""
    request_id: str
    timestamp: str
    status: str
    duration_ms: float
    error: str | None = None
    event_summary: str


class FunctionTemplate(BaseModel):
    """Starter template for a new function."""
    id: str
    name: str
    description: str
    source: str
    config: FunctionConfig
    tags: list[str]
    category: str


# ---------------------------------------------------------------------------
# In-memory store (SQLite backing in future)
# ---------------------------------------------------------------------------

class _FunctionRecord:
    """Internal storage record for a function."""

    def __init__(
        self,
        function_id: str,
        name: str,
        description: str,
        source: str,
        config: FunctionConfig,
        tags: list[str],
    ):
        self.id = function_id
        self.name = name
        self.description = description
        self.source = source
        self.config = config
        self.tags = tags
        self.created_at = datetime.now(UTC).isoformat()
        self.last_modified = self.created_at
        self.last_invoked: str | None = None
        self.invoke_count = 0
        self.status = "idle"
        self.last_result: dict[str, Any] | None = None
        self.logs: list[InvocationLog] = []

    def to_summary(self) -> FunctionSummary:
        return FunctionSummary(
            id=self.id,
            name=self.name,
            description=self.description,
            runtime=self.config.runtime,
            handler=self.config.handler,
            timeout=self.config.timeout,
            memory_mb=self.config.memory_mb,
            tags=self.tags,
            source_lines=self.source.count("\n") + 1 if self.source else 0,
            last_modified=self.last_modified,
            last_invoked=self.last_invoked,
            invoke_count=self.invoke_count,
            status=self.status,
        )

    def to_detail(self) -> FunctionDetail:
        return FunctionDetail(
            id=self.id,
            name=self.name,
            description=self.description,
            source=self.source,
            config=self.config,
            tags=self.tags,
            created_at=self.created_at,
            last_modified=self.last_modified,
            last_invoked=self.last_invoked,
            invoke_count=self.invoke_count,
            status=self.status,
            last_result=self.last_result,
        )


_functions: dict[str, _FunctionRecord] = {}


def _seed_defaults() -> None:
    """Seed a sample function on first access."""
    if _functions:
        return

    sample = _FunctionRecord(
        function_id="fn-hello-world",
        name="hello_world",
        description="A simple greeting function — like your first Lambda.",
        source='''"""Hello World function — returns a greeting."""

def handler(event, context):
    """Process the event and return a greeting.

    Args:
        event: dict with optional 'name' key
        context: execution context (request_id, timeout, etc.)
    """
    name = event.get("name", "World")
    greeting = f"Hello, {name}! 👋"

    print(f"Processing greeting for: {name}")
    print(f"Request ID: {context.get('request_id', 'unknown')}")

    return {
        "statusCode": 200,
        "body": greeting,
        "event_keys": list(event.keys()),
    }
''',
        config=FunctionConfig(timeout=10, memory_mb=128, handler="handler"),
        tags=["starter", "example"],
    )
    _functions[sample.id] = sample

    etl = _FunctionRecord(
        function_id="fn-data-processor",
        name="data_processor",
        description="Extract, validate, and transform a data payload.",
        source='''"""Data processing function — ETL in a single function."""

import json
from datetime import datetime, UTC


def handler(event, context):
    """Process incoming data records.

    Expects event with 'records' list. Each record gets:
    1. Schema validation
    2. Timestamp enrichment
    3. Key normalization
    """
    records = event.get("records", [])
    if not records:
        return {"statusCode": 400, "error": "No records provided"}

    processed = []
    errors = []

    for i, record in enumerate(records):
        try:
            # Validate required fields
            if "id" not in record:
                raise ValueError(f"Record {i} missing 'id'")

            # Enrich with metadata
            enriched = {
                **{k.lower().replace(" ", "_"): v for k, v in record.items()},
                "processed_at": datetime.now(UTC).isoformat(),
                "request_id": context.get("request_id", "unknown"),
                "record_index": i,
            }
            processed.append(enriched)
            print(f"✓ Record {i}: {record.get('id', '?')}")

        except Exception as e:
            errors.append({"index": i, "error": str(e)})
            print(f"✗ Record {i}: {e}")

    return {
        "statusCode": 200,
        "processed": len(processed),
        "errors": len(errors),
        "results": processed[:5],  # Preview first 5
        "error_details": errors,
    }
''',
        config=FunctionConfig(timeout=30, memory_mb=256, handler="handler"),
        tags=["etl", "data", "example"],
    )
    _functions[etl.id] = etl

    webhook = _FunctionRecord(
        function_id="fn-webhook-handler",
        name="webhook_handler",
        description="Process incoming webhook payloads with validation.",
        source='''"""Webhook handler — validate, parse, and route webhooks."""

import hashlib
import json


def handler(event, context):
    """Handle incoming webhook payload.

    Validates the payload signature, extracts the event type,
    and routes to the appropriate handler.
    """
    headers = event.get("headers", {})
    body = event.get("body", {})
    method = event.get("method", "POST")

    print(f"Received {method} webhook")
    print(f"Headers: {json.dumps(headers, indent=2)}")

    # Validate content type
    content_type = headers.get("content-type", "")
    if "json" not in content_type and body:
        return {"statusCode": 400, "error": "Expected JSON content type"}

    # Extract event type
    event_type = (
        headers.get("x-event-type")
        or body.get("type")
        or body.get("event")
        or "unknown"
    )
    print(f"Event type: {event_type}")

    # Generate idempotency key
    payload_hash = hashlib.md5(
        json.dumps(body, sort_keys=True).encode()
    ).hexdigest()[:12]

    # Route by event type
    routes = {
        "push": "process_push",
        "pull_request": "process_pr",
        "issue": "process_issue",
        "deployment": "process_deploy",
    }

    handler_name = routes.get(event_type, "process_unknown")
    print(f"Routing to: {handler_name}")

    return {
        "statusCode": 200,
        "event_type": event_type,
        "handler": handler_name,
        "idempotency_key": payload_hash,
        "body_keys": list(body.keys()) if isinstance(body, dict) else [],
        "processed": True,
    }
''',
        config=FunctionConfig(timeout=15, memory_mb=128, handler="handler"),
        tags=["webhook", "api", "example"],
    )
    _functions[webhook.id] = webhook


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_TEMPLATES: list[FunctionTemplate] = [
    FunctionTemplate(
        id="tpl-blank",
        name="Blank Function",
        description="Empty function with handler signature.",
        category="basic",
        tags=["starter"],
        config=FunctionConfig(),
        source='''"""My function."""


def handler(event, context):
    """Process the event.

    Args:
        event: Input payload (dict)
        context: Execution context with request_id, timeout, etc.

    Returns:
        dict: Response payload
    """
    # Your code here
    return {
        "statusCode": 200,
        "body": "Hello from spine!",
    }
''',
    ),
    FunctionTemplate(
        id="tpl-api-handler",
        name="API Request Handler",
        description="Make HTTP requests to external APIs.",
        category="integration",
        tags=["api", "http"],
        config=FunctionConfig(timeout=30),
        source='''"""API Request Handler — fetch data from external services."""

import json
from urllib.request import urlopen, Request
from urllib.error import URLError


def handler(event, context):
    """Fetch data from an API endpoint.

    Event keys:
        url (str): The URL to fetch
        method (str): HTTP method (default: GET)
        headers (dict): Additional headers
    """
    url = event.get("url", "https://httpbin.org/json")
    method = event.get("method", "GET")
    headers = event.get("headers", {})

    print(f"{method} {url}")

    try:
        req = Request(url, method=method, headers=headers)
        with urlopen(req, timeout=context.get("timeout", 10)) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)

            print(f"Status: {resp.status}")
            print(f"Content-Length: {len(body)}")

            return {
                "statusCode": resp.status,
                "body": data,
                "content_length": len(body),
            }

    except URLError as e:
        print(f"Error: {e}")
        return {"statusCode": 500, "error": str(e)}
''',
    ),
    FunctionTemplate(
        id="tpl-data-transform",
        name="Data Transformer",
        description="Transform and validate data records.",
        category="data",
        tags=["etl", "transform"],
        config=FunctionConfig(timeout=60, memory_mb=256),
        source='''"""Data Transformer — clean, validate, and reshape records."""

from datetime import datetime, UTC


def handler(event, context):
    """Transform a batch of records.

    Event keys:
        records (list[dict]): Input records
        schema (dict): Optional field mapping {old_name: new_name}
    """
    records = event.get("records", [])
    schema = event.get("schema", {})

    print(f"Processing {len(records)} records")

    results = []
    for i, record in enumerate(records):
        # Apply field mapping
        if schema:
            record = {schema.get(k, k): v for k, v in record.items()}

        # Add metadata
        record["_processed_at"] = datetime.now(UTC).isoformat()
        record["_index"] = i

        # Normalize string fields
        for key, val in record.items():
            if isinstance(val, str):
                record[key] = val.strip()

        results.append(record)

    print(f"Transformed {len(results)} records")

    return {
        "statusCode": 200,
        "record_count": len(results),
        "sample": results[:3],
    }
''',
    ),
    FunctionTemplate(
        id="tpl-scheduled-task",
        name="Scheduled Task",
        description="Template for a periodic/cron-triggered function.",
        category="automation",
        tags=["cron", "scheduled"],
        config=FunctionConfig(timeout=120, memory_mb=256),
        source='''"""Scheduled Task — runs on a timer/cron trigger."""

from datetime import datetime, UTC


def handler(event, context):
    """Execute scheduled maintenance/cleanup/report.

    Event keys (auto-populated by scheduler):
        schedule_name (str): Name of the schedule that triggered this
        scheduled_time (str): ISO timestamp of intended run time
        attempt (int): Retry attempt number (1-based)
    """
    schedule = event.get("schedule_name", "manual")
    attempt = event.get("attempt", 1)

    print(f"Running scheduled task: {schedule} (attempt {attempt})")
    print(f"Current time: {datetime.now(UTC).isoformat()}")

    # Simulate work
    tasks_completed = []

    # Task 1: Check thresholds
    print("Checking thresholds...")
    tasks_completed.append("threshold_check")

    # Task 2: Cleanup old data
    print("Cleaning up stale records...")
    tasks_completed.append("cleanup")

    # Task 3: Generate report
    print("Generating summary report...")
    tasks_completed.append("report")

    return {
        "statusCode": 200,
        "schedule": schedule,
        "tasks_completed": tasks_completed,
        "duration_hint": "< 1s (simulated)",
    }
''',
    ),
]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=PagedResponse[FunctionSummary])
async def list_functions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tag: str | None = Query(default=None, description="Filter by tag"),
    search: str | None = Query(default=None, description="Search name/description"),
    sort: str = Query(default="last_modified", description="Sort by field"),
):
    """List all saved functions."""
    _seed_defaults()

    items = list(_functions.values())

    # Filter by tag
    if tag:
        items = [f for f in items if tag in f.tags]

    # Search filter
    if search:
        q = search.lower()
        items = [
            f for f in items
            if q in f.name.lower() or q in f.description.lower()
        ]

    # Sort
    if sort == "name":
        items.sort(key=lambda f: f.name)
    elif sort == "invoke_count":
        items.sort(key=lambda f: f.invoke_count, reverse=True)
    else:
        items.sort(key=lambda f: f.last_modified, reverse=True)

    total = len(items)
    items = items[offset : offset + limit]

    return PagedResponse(
        data=[f.to_summary() for f in items],
        page=PageMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + limit < total,
        ),
    )


@router.post("", response_model=SuccessResponse[FunctionDetail], status_code=201)
async def create_function(body: FunctionCreate):
    """Create a new function."""
    _seed_defaults()

    # Check for name conflicts
    for fn in _functions.values():
        if fn.name == body.name:
            raise HTTPException(409, f"Function named '{body.name}' already exists")

    function_id = f"fn-{uuid.uuid4().hex[:12]}"
    record = _FunctionRecord(
        function_id=function_id,
        name=body.name,
        description=body.description,
        source=body.source,
        config=body.config,
        tags=body.tags,
    )
    _functions[function_id] = record

    return SuccessResponse(data=record.to_detail())


@router.get("/templates", response_model=SuccessResponse[list[FunctionTemplate]])
async def list_templates():
    """List available function templates."""
    return SuccessResponse(data=_TEMPLATES)


@router.get("/{function_id}", response_model=SuccessResponse[FunctionDetail])
async def get_function(function_id: str):
    """Get full function details including source code."""
    _seed_defaults()

    record = _functions.get(function_id)
    if record is None:
        raise HTTPException(404, f"Function '{function_id}' not found")

    return SuccessResponse(data=record.to_detail())


@router.put("/{function_id}", response_model=SuccessResponse[FunctionDetail])
async def update_function(function_id: str, body: FunctionUpdate):
    """Update a function's source code, config, or metadata."""
    _seed_defaults()

    record = _functions.get(function_id)
    if record is None:
        raise HTTPException(404, f"Function '{function_id}' not found")

    if body.name is not None:
        # Check name uniqueness
        for fn in _functions.values():
            if fn.name == body.name and fn.id != function_id:
                raise HTTPException(409, f"Function named '{body.name}' already exists")
        record.name = body.name
    if body.description is not None:
        record.description = body.description
    if body.source is not None:
        record.source = body.source
    if body.config is not None:
        record.config = body.config
    if body.tags is not None:
        record.tags = body.tags

    record.last_modified = datetime.now(UTC).isoformat()

    return SuccessResponse(data=record.to_detail())


@router.delete("/{function_id}", response_model=SuccessResponse[dict])
async def delete_function(function_id: str):
    """Delete a function."""
    _seed_defaults()

    record = _functions.pop(function_id, None)
    if record is None:
        raise HTTPException(404, f"Function '{function_id}' not found")

    return SuccessResponse(data={"deleted": function_id, "name": record.name})


@router.post("/{function_id}/invoke", response_model=SuccessResponse[InvokeResult])
async def invoke_function(function_id: str, body: InvokeRequest | None = None):
    """Invoke (execute) a function — like Lambda's Invoke API.

    Writes the function source to a temp file with a wrapper that calls
    the handler, captures stdout, and returns the result as JSON.
    Execution runs in a subprocess with timeout enforcement.
    """
    _seed_defaults()

    if body is None:
        body = InvokeRequest()

    record = _functions.get(function_id)
    if record is None:
        raise HTTPException(404, f"Function '{function_id}' not found")

    if body.dry_run:
        return SuccessResponse(data=InvokeResult(
            request_id=f"dry-{uuid.uuid4().hex[:8]}",
            function_id=function_id,
            function_name=record.name,
            status="dry_run",
            result=None,
            logs="[DRY RUN] Would execute with event: " + json.dumps(body.event),
            duration_ms=0,
            billed_duration_ms=0,
            started_at=datetime.now(UTC).isoformat(),
            ended_at=datetime.now(UTC).isoformat(),
        ))

    record.status = "running"
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    timeout = body.timeout or record.config.timeout
    started_at = datetime.now(UTC)

    # Build execution wrapper
    wrapper = _build_execution_wrapper(
        source=record.source,
        handler_name=record.config.handler,
        event=body.event,
        context={
            "request_id": request_id,
            "function_name": record.name,
            "function_id": function_id,
            "timeout": timeout,
            "memory_mb": record.config.memory_mb,
            **body.context,
        },
    )

    # Write to temp file and execute
    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", prefix="spine_fn_", delete=False,
            encoding="utf-8",
        )
        tmp.write(wrapper)
        tmp.close()

        # Set environment
        env = {**os.environ}
        env.update(record.config.env_vars)
        env["SPINE_FUNCTION_ID"] = function_id
        env["SPINE_REQUEST_ID"] = request_id
        env["PYTHONIOENCODING"] = "utf-8"

        def _run_subprocess() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, tmp.name],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                encoding="utf-8",
                errors="replace",
            )

        try:
            completed = await asyncio.to_thread(_run_subprocess)
            stdout_str = completed.stdout or ""
            stderr_str = completed.stderr or ""
        except subprocess.TimeoutExpired:
            ended_at = datetime.now(UTC)
            duration = (ended_at - started_at).total_seconds() * 1000

            record.status = "error"
            record.invoke_count += 1
            record.last_invoked = ended_at.isoformat()

            result = InvokeResult(
                request_id=request_id,
                function_id=function_id,
                function_name=record.name,
                status="timeout",
                error=f"Function timed out after {timeout}s",
                error_type="TimeoutError",
                logs=f"START RequestId: {request_id}\nFunction timed out after {timeout}s\nEND RequestId: {request_id}\n",
                duration_ms=duration,
                billed_duration_ms=duration,
                started_at=started_at.isoformat(),
                ended_at=ended_at.isoformat(),
            )
            record.last_result = result.model_dump()
            _record_log(record, result, body.event)
            return SuccessResponse(data=result)

        ended_at = datetime.now(UTC)
        duration = (ended_at - started_at).total_seconds() * 1000

        # Parse result from stdout (last line is JSON envelope)
        func_result = None
        func_logs = ""
        error_msg = None
        error_type = None
        status = "success"

        lines = stdout_str.strip().split("\n") if stdout_str.strip() else []

        if lines:
            # Last line should be our JSON result envelope
            try:
                envelope = json.loads(lines[-1])
                func_result = envelope.get("result")
                error_msg = envelope.get("error")
                error_type = envelope.get("error_type")
                if error_msg:
                    status = "error"
                # Everything except the last line is user logs
                func_logs = "\n".join(lines[:-1])
            except json.JSONDecodeError:
                # No valid envelope — treat all output as logs
                func_logs = stdout_str
                if completed.returncode != 0:
                    status = "error"
                    error_msg = stderr_str or "Process exited with non-zero code"
                    error_type = "RuntimeError"

        if stderr_str and status == "error":
            func_logs += "\n" + stderr_str

        # Build formatted log output (Lambda-style)
        formatted_logs = (
            f"START RequestId: {request_id}\n"
            f"{func_logs}\n"
            f"END RequestId: {request_id}\n"
            f"REPORT RequestId: {request_id}\tDuration: {duration:.1f} ms\t"
            f"Billed Duration: {max(1, int(duration))} ms\t"
            f"Memory Size: {record.config.memory_mb} MB\n"
        )

        record.status = "idle" if status == "success" else "error"
        record.invoke_count += 1
        record.last_invoked = ended_at.isoformat()

        result = InvokeResult(
            request_id=request_id,
            function_id=function_id,
            function_name=record.name,
            status=status,
            result=func_result,
            logs=formatted_logs,
            error=error_msg,
            error_type=error_type,
            duration_ms=round(duration, 1),
            billed_duration_ms=max(1.0, round(duration, 1)),
            started_at=started_at.isoformat(),
            ended_at=ended_at.isoformat(),
        )
        record.last_result = result.model_dump()
        _record_log(record, result, body.event)

        return SuccessResponse(data=result)

    except Exception as e:
        ended_at = datetime.now(UTC)
        duration = (ended_at - started_at).total_seconds() * 1000
        record.status = "error"
        logger.exception("Function invoke failed for %s", function_id)

        result = InvokeResult(
            request_id=request_id,
            function_id=function_id,
            function_name=record.name,
            status="error",
            error=str(e),
            error_type=type(e).__name__,
            logs=f"START RequestId: {request_id}\nINTERNAL ERROR: {e}\nEND RequestId: {request_id}\n",
            duration_ms=round(duration, 1),
            billed_duration_ms=max(1.0, round(duration, 1)),
            started_at=started_at.isoformat(),
            ended_at=ended_at.isoformat(),
        )
        record.last_result = result.model_dump()
        return SuccessResponse(data=result)

    finally:
        if tmp and Path(tmp.name).exists():
            try:
                Path(tmp.name).unlink()
            except OSError:
                pass


@router.get("/{function_id}/logs", response_model=SuccessResponse[list[InvocationLog]])
async def get_function_logs(
    function_id: str,
    limit: int = Query(default=20, ge=1, le=100),
):
    """Get recent invocation logs for a function."""
    _seed_defaults()

    record = _functions.get(function_id)
    if record is None:
        raise HTTPException(404, f"Function '{function_id}' not found")

    logs = record.logs[-limit:]
    logs.reverse()  # Most recent first

    return SuccessResponse(data=logs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_execution_wrapper(
    source: str,
    handler_name: str,
    event: dict,
    context: dict,
) -> str:
    """Build a Python script that executes the user function safely.

    The wrapper:
    1. Defines the user's source code
    2. Calls handler(event, context)
    3. Prints the result as a JSON envelope on the last line
    """
    return f'''
import json
import sys
import traceback

# ── User function source ──────────────────────────────
{source}
# ── End user source ───────────────────────────────────

if __name__ == "__main__":
    _event = json.loads({json.dumps(json.dumps(event))})
    _context = json.loads({json.dumps(json.dumps(context))})

    try:
        _result = {handler_name}(_event, _context)
        print(json.dumps({{"result": _result, "error": None, "error_type": None}}))
    except Exception as _e:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({{
            "result": None,
            "error": str(_e),
            "error_type": type(_e).__name__,
        }}))
        sys.exit(1)
'''


def _record_log(
    record: _FunctionRecord,
    result: InvokeResult,
    event: dict,
) -> None:
    """Append an invocation log entry."""
    event_keys = list(event.keys()) if event else []
    summary = (
        f"keys=[{', '.join(event_keys[:5])}]"
        if event_keys
        else "(empty event)"
    )

    record.logs.append(InvocationLog(
        request_id=result.request_id,
        timestamp=result.started_at,
        status=result.status,
        duration_ms=result.duration_ms,
        error=result.error,
        event_summary=summary,
    ))

    # Keep last 50 logs
    if len(record.logs) > 50:
        record.logs = record.logs[-50:]
