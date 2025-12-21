"""
Playground router — interactive workflow execution in the browser.

Exposes the WorkflowPlayground as a stateful REST API so the frontend
can step through workflows, inspect context, modify params, and rewind —
all without leaving the browser.

Endpoints:
    GET  /playground/sessions              List active playground sessions
    POST /playground/sessions              Create a new playground session
    GET  /playground/sessions/{sid}        Get session state / summary
    DELETE /playground/sessions/{sid}      Destroy a session

    POST /playground/sessions/{sid}/step       Execute next step
    POST /playground/sessions/{sid}/step-back  Rewind one step
    POST /playground/sessions/{sid}/run-to     Run to a named step
    POST /playground/sessions/{sid}/run-all    Run all remaining steps
    POST /playground/sessions/{sid}/reset      Reset to initial state

    GET  /playground/sessions/{sid}/peek       Preview next step
    GET  /playground/sessions/{sid}/context    Current context snapshot
    GET  /playground/sessions/{sid}/history    Full step history

    POST /playground/sessions/{sid}/params     Set param(s)

    GET  /playground/workflows                 List workflows available to load
    GET  /playground/examples                  Pre-built example snippets

Manifesto:
    Interactive workflow exploration needs a safe sandbox where
    users can step through execution without touching production data.

Tags:
    spine-core, api, playground, interactive, debugging

Doc-Types: API_REFERENCE
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from spine.api.schemas.common import PagedResponse, PageMeta, SuccessResponse

router = APIRouter(prefix="/playground")


# ---------------------------------------------------------------------------
# In-memory session store
# ---------------------------------------------------------------------------

_sessions: dict[str, _PlaygroundSession] = {}

MAX_SESSIONS = 20
SESSION_TIMEOUT_SECONDS = 3600  # 1 hour


class _PlaygroundSession:
    """Wraps a WorkflowPlayground with metadata."""

    def __init__(self, session_id: str, workflow_name: str, params: dict[str, Any]):
        from spine.orchestration.playground import WorkflowPlayground
        from spine.orchestration.workflow_registry import get_workflow

        self.session_id = session_id
        self.workflow_name = workflow_name
        self.initial_params = dict(params)
        self.created_at = time.time()
        self.last_accessed = time.time()

        workflow = get_workflow(workflow_name)
        if workflow is None:
            raise ValueError(f"Workflow {workflow_name!r} not found in registry")

        self.playground = WorkflowPlayground()
        self.playground.load(workflow, params=params, run_id=session_id)

    def touch(self) -> None:
        self.last_accessed = time.time()

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.last_accessed) > SESSION_TIMEOUT_SECONDS


def _gc_sessions() -> None:
    """Remove expired sessions."""
    expired = [sid for sid, s in _sessions.items() if s.is_expired]
    for sid in expired:
        del _sessions[sid]


def _get_session(sid: str) -> _PlaygroundSession:
    _gc_sessions()
    session = _sessions.get(sid)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {sid!r} not found")
    session.touch()
    return session


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class CreateSessionRequest(BaseModel):
    """Create a new playground session."""
    workflow_name: str = Field(..., description="Name of the workflow to load")
    params: dict[str, Any] = Field(default_factory=dict, description="Initial parameters")


class SetParamsRequest(BaseModel):
    """Update one or more context parameters."""
    params: dict[str, Any] = Field(..., description="Key-value pairs to set")


class RunToRequest(BaseModel):
    """Run to a specific named step (inclusive)."""
    step_name: str = Field(..., description="Name of the step to run to")


class SessionSummary(BaseModel):
    """Summary of a playground session."""
    session_id: str
    workflow_name: str
    total_steps: int
    executed: int
    remaining: int
    is_complete: bool
    created_at: float
    last_accessed: float


class StepSnapshotSchema(BaseModel):
    """A single step execution result."""
    step_name: str
    step_type: str
    status: str  # completed | failed | skipped
    result: dict[str, Any] | None = None
    context_before: dict[str, Any] = Field(default_factory=dict)
    context_after: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float
    error: str | None = None
    step_index: int = 0


class StepPreview(BaseModel):
    """Preview of the next step (without executing)."""
    name: str
    step_type: str
    operation_name: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class ContextSnapshot(BaseModel):
    """Current workflow context."""
    run_id: str
    workflow_name: str
    params: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)


class PlaygroundWorkflow(BaseModel):
    """A workflow available for playground use."""
    name: str
    description: str
    step_count: int
    domain: str
    tags: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)


class PlaygroundExample(BaseModel):
    """A pre-built example workflow with sample params."""
    id: str
    title: str
    description: str
    workflow_name: str
    params: dict[str, Any] = Field(default_factory=dict)
    code_snippet: str = ""
    category: str = "general"


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@router.get("/sessions", response_model=PagedResponse[SessionSummary])
def list_sessions():
    """List all active playground sessions."""
    _gc_sessions()
    items = []
    for s in _sessions.values():
        summary = s.playground.summary()
        items.append(SessionSummary(
            session_id=s.session_id,
            workflow_name=s.workflow_name,
            total_steps=summary["total_steps"],
            executed=summary["executed"],
            remaining=summary["remaining"],
            is_complete=summary["is_complete"],
            created_at=s.created_at,
            last_accessed=s.last_accessed,
        ))
    return PagedResponse(
        data=items,
        page=PageMeta(total=len(items), limit=100, offset=0, has_more=False),
    )


@router.post("/sessions", response_model=SuccessResponse[SessionSummary], status_code=201)
def create_session(body: CreateSessionRequest):
    """Create a new interactive playground session.

    Loads the specified workflow and prepares it for step-by-step
    execution. Returns the session ID to use in subsequent calls.
    """
    _gc_sessions()

    if len(_sessions) >= MAX_SESSIONS:
        raise HTTPException(
            status_code=429,
            detail=f"Maximum {MAX_SESSIONS} concurrent sessions — close an existing one first",
        )

    session_id = str(uuid.uuid4())[:8]

    try:
        session = _PlaygroundSession(session_id, body.workflow_name, body.params)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    _sessions[session_id] = session
    summary = session.playground.summary()

    return SuccessResponse(
        data=SessionSummary(
            session_id=session_id,
            workflow_name=session.workflow_name,
            total_steps=summary["total_steps"],
            executed=summary["executed"],
            remaining=summary["remaining"],
            is_complete=summary["is_complete"],
            created_at=session.created_at,
            last_accessed=session.last_accessed,
        ),
    )


@router.get("/sessions/{sid}", response_model=SuccessResponse[SessionSummary])
def get_session(sid: str = Path(..., description="Session ID")):
    """Get the current state of a playground session."""
    session = _get_session(sid)
    summary = session.playground.summary()
    return SuccessResponse(
        data=SessionSummary(
            session_id=session.session_id,
            workflow_name=session.workflow_name,
            total_steps=summary["total_steps"],
            executed=summary["executed"],
            remaining=summary["remaining"],
            is_complete=summary["is_complete"],
            created_at=session.created_at,
            last_accessed=session.last_accessed,
        ),
    )


@router.delete("/sessions/{sid}")
def delete_session(sid: str = Path(..., description="Session ID")):
    """Destroy a playground session and free resources."""
    if sid not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session {sid!r} not found")
    del _sessions[sid]
    return {"status": "deleted", "session_id": sid}


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------

def _snapshot_to_schema(snap: Any) -> StepSnapshotSchema:
    """Convert a StepSnapshot dataclass to the API schema."""
    result_dict = None
    if snap.result is not None:
        result_dict = {
            "success": snap.result.success,
            "output": snap.result.output,
            "error": snap.result.error,
        }
    return StepSnapshotSchema(
        step_name=snap.step_name,
        step_type=snap.step_type.value,
        status=snap.status,
        result=result_dict,
        context_before=snap.context_before,
        context_after=snap.context_after,
        duration_ms=round(snap.duration_ms, 2),
        error=snap.error,
        step_index=snap.step_index,
    )


@router.post("/sessions/{sid}/step", response_model=SuccessResponse[StepSnapshotSchema])
def step(sid: str = Path(...)):
    """Execute the next step in the workflow.

    Returns the step snapshot with before/after context, result, and timing.
    """
    session = _get_session(sid)
    try:
        snap = session.playground.step()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return SuccessResponse(data=_snapshot_to_schema(snap))


@router.post("/sessions/{sid}/step-back", response_model=SuccessResponse[StepSnapshotSchema | None])
def step_back(sid: str = Path(...)):
    """Rewind one step (undo the last execution).

    Returns the undone snapshot, or null if there's nothing to undo.
    """
    session = _get_session(sid)
    snap = session.playground.step_back()
    if snap is None:
        return SuccessResponse(data=None)
    return SuccessResponse(data=_snapshot_to_schema(snap))


@router.post("/sessions/{sid}/run-to", response_model=SuccessResponse[list[StepSnapshotSchema]])
def run_to(sid: str = Path(...), body: RunToRequest = ...):
    """Run through steps until the named step (inclusive)."""
    session = _get_session(sid)
    try:
        snaps = session.playground.run_to(body.step_name)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return SuccessResponse(data=[_snapshot_to_schema(s) for s in snaps])


@router.post("/sessions/{sid}/run-all", response_model=SuccessResponse[list[StepSnapshotSchema]])
def run_all(sid: str = Path(...)):
    """Execute all remaining steps at once."""
    session = _get_session(sid)
    try:
        snaps = session.playground.run_all()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return SuccessResponse(data=[_snapshot_to_schema(s) for s in snaps])


@router.post("/sessions/{sid}/reset")
def reset_session(sid: str = Path(...)):
    """Reset the session to its initial state (re-load workflow)."""
    session = _get_session(sid)
    session.playground.reset()
    summary = session.playground.summary()
    return SuccessResponse(
        data=SessionSummary(
            session_id=session.session_id,
            workflow_name=session.workflow_name,
            total_steps=summary["total_steps"],
            executed=summary["executed"],
            remaining=summary["remaining"],
            is_complete=summary["is_complete"],
            created_at=session.created_at,
            last_accessed=session.last_accessed,
        ),
    )


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------

@router.get("/sessions/{sid}/peek", response_model=SuccessResponse[StepPreview | None])
def peek(sid: str = Path(...)):
    """Preview the next step without executing it."""
    session = _get_session(sid)
    step_obj = session.playground.peek()
    if step_obj is None:
        return SuccessResponse(data=None)
    return SuccessResponse(data=StepPreview(
        name=step_obj.name,
        step_type=step_obj.step_type.value,
        operation_name=getattr(step_obj, "operation_name", None),
        depends_on=list(step_obj.depends_on) if step_obj.depends_on else [],
        config=dict(step_obj.config) if step_obj.config else {},
    ))


@router.get("/sessions/{sid}/context", response_model=SuccessResponse[ContextSnapshot])
def get_context(sid: str = Path(...)):
    """Get the current workflow context (params + accumulated outputs)."""
    session = _get_session(sid)
    ctx = session.playground.context
    if ctx is None:
        raise HTTPException(status_code=400, detail="No context available")
    return SuccessResponse(data=ContextSnapshot(
        run_id=ctx.run_id,
        workflow_name=ctx.workflow_name,
        params=dict(ctx.params),
        outputs=dict(ctx.outputs),
    ))


@router.get("/sessions/{sid}/history", response_model=SuccessResponse[list[StepSnapshotSchema]])
def get_history(sid: str = Path(...)):
    """Get the full execution history of this session."""
    session = _get_session(sid)
    return SuccessResponse(
        data=[_snapshot_to_schema(s) for s in session.playground.history],
    )


# ---------------------------------------------------------------------------
# Parameter modification
# ---------------------------------------------------------------------------

@router.post("/sessions/{sid}/params")
def set_params(sid: str = Path(...), body: SetParamsRequest = ...):
    """Set one or more context parameters on the fly.

    Changes take effect for the *next* step execution. Previous
    steps are not affected.
    """
    session = _get_session(sid)
    session.playground.set_params(body.params)
    ctx = session.playground.context
    return SuccessResponse(data={
        "params": dict(ctx.params) if ctx else {},
        "updated_keys": list(body.params.keys()),
    })


# ---------------------------------------------------------------------------
# Workflow catalog (what can be loaded into the playground)
# ---------------------------------------------------------------------------

@router.get("/workflows", response_model=PagedResponse[PlaygroundWorkflow])
def list_playground_workflows():
    """List all registered workflows available for playground use."""
    from spine.orchestration.workflow_registry import list_workflows, get_workflow

    workflow_names = list_workflows()
    items = []
    for name in workflow_names:
        try:
            wf = get_workflow(name)
        except Exception:
            continue
        steps_info = []
        for s in wf.steps:
            steps_info.append({
                "name": s.name,
                "type": s.step_type.value,
                "operation": getattr(s, "operation_name", None),
                "depends_on": list(s.depends_on) if s.depends_on else [],
            })
        items.append(PlaygroundWorkflow(
            name=wf.name,
            description=wf.description or "",
            step_count=len(wf.steps),
            domain=wf.domain or "",
            tags=list(wf.tags) if wf.tags else [],
            steps=steps_info,
        ))
    return PagedResponse(
        data=items,
        page=PageMeta(total=len(items), limit=100, offset=0, has_more=False),
    )


# ---------------------------------------------------------------------------
# Pre-built examples with sample code + params
# ---------------------------------------------------------------------------

_PLAYGROUND_EXAMPLES: list[PlaygroundExample] = [
    PlaygroundExample(
        id="etl-basic",
        title="Basic ETL Operation",
        description="Step through a 4-stage ETL: extract → validate → transform → load",
        workflow_name="etl.daily_ingest",
        params={"date": "2026-02-18", "source": "sec_filings", "batch_size": 100},
        category="data-engineering",
        code_snippet="""from spine.orchestration import Workflow, Step

workflow = Workflow(
    name="etl.daily_ingest",
    domain="core",
    steps=[
        Step.operation("extract", "core.extract"),
        Step.operation("validate", "core.validate",
                      depends_on=["extract"]),
        Step.operation("transform", "core.transform",
                      depends_on=["validate"]),
        Step.operation("load", "core.load",
                      depends_on=["transform"]),
    ],
)

# In the playground, click ▶ Step to execute one step at a time.
# Inspect the context panel to see outputs accumulate.
# Modify params in the editor and re-run steps.""",
    ),
    PlaygroundExample(
        id="quality-scan",
        title="Quality Scan Workflow",
        description="Run schema checks, completeness, business rules, and generate a report",
        workflow_name="quality.full_scan",
        params={"dataset": "sec_10k", "threshold": 0.95, "strict": True},
        category="quality",
        code_snippet="""from spine.orchestration import Workflow, Step

workflow = Workflow(
    name="quality.full_scan",
    domain="quality",
    steps=[
        Step.operation("schema_check", "quality.schema"),
        Step.operation("completeness", "quality.completeness"),
        Step.operation("business_rules", "quality.rules",
                      depends_on=["schema_check", "completeness"]),
        Step.operation("report", "quality.report",
                      depends_on=["business_rules"]),
    ],
)

# Try stepping through and modifying the threshold param
# between steps to see how it affects downstream results.""",
    ),
    PlaygroundExample(
        id="weekly-report",
        title="Weekly Report Generation",
        description="Aggregate data, render reports, and distribute to stakeholders",
        workflow_name="reporting.weekly_summary",
        params={"week": "2026-W07", "format": "html", "recipients": ["team@example.com"]},
        category="reporting",
        code_snippet="""from spine.orchestration import Workflow, Step

workflow = Workflow(
    name="reporting.weekly_summary",
    domain="reporting",
    steps=[
        Step.operation("aggregate", "reporting.aggregate"),
        Step.operation("render", "reporting.render",
                      depends_on=["aggregate"]),
        Step.operation("distribute", "reporting.distribute",
                      depends_on=["render"]),
    ],
)

# Use step_back() to rewind after the render step,
# change the format param to 'pdf', then re-step.""",
    ),
    PlaygroundExample(
        id="playground-repl",
        title="Interactive REPL Demo",
        description="Shows step, step_back, set_param, and run_all in action",
        workflow_name="etl.daily_ingest",
        params={"date": "2026-02-18", "mode": "incremental"},
        category="tutorial",
        code_snippet="""# This example demonstrates the playground REPL capabilities.
#
# 1. Click ▶ Step to execute "extract"
# 2. Inspect the Context panel — see params and outputs
# 3. Click ◀ Step Back to rewind
# 4. Edit the params JSON — change mode to "full"
# 5. Click ▶ Step again — runs with updated params
# 6. Click ▶▶ Run All to execute remaining steps
# 7. Review the History panel for the full execution trace
#
# The playground runs in dry-run mode by default —
# operation steps return stub results so you can
# explore workflow structure without side effects.""",
    ),
]


@router.get("/examples", response_model=PagedResponse[PlaygroundExample])
def list_examples(
    category: str | None = Query(None, description="Filter by category"),
):
    """List pre-built playground examples with sample code and params.

    Each example includes a workflow name, suggested params, and a
    Python code snippet showing how the workflow is defined.
    """
    items = _PLAYGROUND_EXAMPLES
    if category:
        items = [e for e in items if e.category == category]
    return PagedResponse(
        data=items,
        page=PageMeta(total=len(items), limit=100, offset=0, has_more=False),
    )
