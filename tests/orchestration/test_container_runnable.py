"""Tests for Idea #4 — ContainerRunnable.

Covers:
- spec building from pipeline name/params
- image resolver hook
- command template substitution
- env var mapping (params → SPINE_PARAM_*)
- poll-until-done with mocked engine
- timeout handling
- Runnable protocol conformance
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spine.execution.runnable import PipelineRunResult, Runnable
from spine.execution.runtimes._types import ContainerJobSpec, JobStatus
from spine.execution.runtimes.engine import SubmitResult
from spine.orchestration.container_runnable import ContainerRunnable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine_mock(
    *,
    submit_result: SubmitResult | None = None,
    status_sequence: list[JobStatus] | None = None,
) -> MagicMock:
    """Create a mock JobEngine with async submit/status."""
    engine = MagicMock()

    if submit_result is None:
        submit_result = SubmitResult(
            execution_id="exec-001",
            external_ref="container-abc",
            runtime="local_process",
            spec_hash="sha256:abc",
        )

    async def _submit(spec):
        return submit_result

    engine.submit = AsyncMock(side_effect=_submit)

    if status_sequence is None:
        status_sequence = [
            JobStatus(state="succeeded", exit_code=0),
        ]

    call_count = {"n": 0}

    async def _status(execution_id):
        idx = min(call_count["n"], len(status_sequence) - 1)
        call_count["n"] += 1
        return status_sequence[idx]

    engine.status = AsyncMock(side_effect=_status)

    return engine


# ---------------------------------------------------------------------------
# Spec building
# ---------------------------------------------------------------------------

class TestBuildSpec:
    def test_basic_spec(self):
        engine = _make_engine_mock()
        cr = ContainerRunnable(engine=engine)
        spec = cr._build_spec("my.pipeline", None, None, None)

        assert isinstance(spec, ContainerJobSpec)
        assert spec.name == "pipeline-my-pipeline"
        assert spec.image == "spine-pipeline:latest"
        assert "spine-cli" in spec.command[0]
        assert "my.pipeline" in spec.command[-1]

    def test_params_become_env_vars(self):
        engine = _make_engine_mock()
        cr = ContainerRunnable(engine=engine)
        spec = cr._build_spec("pipe", {"batch_size": 100, "date": "2026-01-15"}, None, None)

        assert spec.env["SPINE_PARAM_BATCH_SIZE"] == "100"
        assert spec.env["SPINE_PARAM_DATE"] == "2026-01-15"

    def test_parent_run_id_in_env(self):
        engine = _make_engine_mock()
        cr = ContainerRunnable(engine=engine)
        spec = cr._build_spec("pipe", None, "run-xyz", None)

        assert spec.env["SPINE_PARENT_RUN_ID"] == "run-xyz"
        assert spec.labels["spine.parent_run_id"] == "run-xyz"

    def test_correlation_id_in_env(self):
        engine = _make_engine_mock()
        cr = ContainerRunnable(engine=engine)
        spec = cr._build_spec("pipe", None, None, "corr-123")

        assert spec.env["SPINE_CORRELATION_ID"] == "corr-123"

    def test_custom_image_resolver(self):
        engine = _make_engine_mock()
        resolver = lambda name: f"registry.io/spine/{name}:v2"
        cr = ContainerRunnable(engine=engine, image_resolver=resolver)
        spec = cr._build_spec("etl.ingest", None, None, None)

        assert spec.image == "registry.io/spine/etl.ingest:v2"

    def test_custom_command_template(self):
        engine = _make_engine_mock()
        cr = ContainerRunnable(
            engine=engine,
            command_template=["python", "-m", "spine.run", "{pipeline}"],
        )
        spec = cr._build_spec("my.pipe", None, None, None)

        assert spec.command == ["python", "-m", "spine.run", "my.pipe"]

    def test_labels_include_pipeline_name(self):
        engine = _make_engine_mock()
        cr = ContainerRunnable(engine=engine)
        spec = cr._build_spec("etl.daily", None, None, None)

        assert spec.labels["spine.pipeline"] == "etl.daily"


# ---------------------------------------------------------------------------
# submit_pipeline_sync
# ---------------------------------------------------------------------------

class TestSubmitPipelineSync:
    def test_success(self):
        engine = _make_engine_mock(
            status_sequence=[JobStatus(state="succeeded", exit_code=0)],
        )
        cr = ContainerRunnable(engine=engine, poll_interval=0.01)
        result = cr.submit_pipeline_sync("my.pipe")

        assert isinstance(result, PipelineRunResult)
        assert result.succeeded
        assert result.status == "completed"
        assert result.run_id == "exec-001"

    def test_failure(self):
        engine = _make_engine_mock(
            status_sequence=[
                JobStatus(
                    state="failed",
                    exit_code=1,
                    message="OOMKilled",
                ),
            ],
        )
        cr = ContainerRunnable(engine=engine, poll_interval=0.01)
        result = cr.submit_pipeline_sync("failing.pipe")

        assert not result.succeeded
        assert result.status == "failed"
        assert result.error == "OOMKilled"

    def test_polls_until_terminal(self):
        engine = _make_engine_mock(
            status_sequence=[
                JobStatus(state="pending"),
                JobStatus(state="running"),
                JobStatus(state="running"),
                JobStatus(state="succeeded", exit_code=0),
            ],
        )
        cr = ContainerRunnable(engine=engine, poll_interval=0.01)
        result = cr.submit_pipeline_sync("slow.pipe")

        assert result.succeeded
        # Should have called status multiple times
        assert engine.status.call_count >= 3

    def test_timeout(self):
        engine = _make_engine_mock(
            status_sequence=[
                JobStatus(state="running"),  # Never completes
            ],
        )
        cr = ContainerRunnable(engine=engine, poll_interval=0.01, timeout=0.05)
        result = cr.submit_pipeline_sync("hanging.pipe")

        assert not result.succeeded
        assert result.status == "failed"
        assert "Timed out" in (result.error or "")

    def test_params_forwarded(self):
        engine = _make_engine_mock()
        cr = ContainerRunnable(engine=engine, poll_interval=0.01)
        cr.submit_pipeline_sync("pipe", params={"key": "val"})

        # Verify submit was called with correct spec
        engine.submit.assert_called_once()
        spec = engine.submit.call_args[0][0]
        assert spec.env["SPINE_PARAM_KEY"] == "val"

    def test_parent_run_id_forwarded(self):
        engine = _make_engine_mock()
        cr = ContainerRunnable(engine=engine, poll_interval=0.01)
        cr.submit_pipeline_sync("pipe", parent_run_id="parent-123")

        spec = engine.submit.call_args[0][0]
        assert spec.env["SPINE_PARENT_RUN_ID"] == "parent-123"

    def test_cancelled_job(self):
        engine = _make_engine_mock(
            status_sequence=[
                JobStatus(state="running"),
                JobStatus(state="cancelled"),
            ],
        )
        cr = ContainerRunnable(engine=engine, poll_interval=0.01)
        result = cr.submit_pipeline_sync("cancelled.pipe")

        assert not result.succeeded
        assert result.status == "failed"
        assert result.metrics.get("runtime_state") == "cancelled"

    def test_metrics_include_exit_code(self):
        engine = _make_engine_mock(
            status_sequence=[JobStatus(state="succeeded", exit_code=0)],
        )
        cr = ContainerRunnable(engine=engine, poll_interval=0.01)
        result = cr.submit_pipeline_sync("pipe")

        assert result.metrics["exit_code"] == 0
        assert result.metrics["execution_id"] == "exec-001"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestProtocol:
    def test_is_runnable(self):
        engine = _make_engine_mock()
        cr = ContainerRunnable(engine=engine)
        assert isinstance(cr, Runnable)

    def test_has_submit_pipeline_sync(self):
        assert hasattr(ContainerRunnable, "submit_pipeline_sync")

    def test_signature_matches_protocol(self):
        import inspect
        sig = inspect.signature(ContainerRunnable.submit_pipeline_sync)
        params = list(sig.parameters.keys())
        assert "pipeline_name" in params
        assert "params" in params
        assert "parent_run_id" in params
        assert "correlation_id" in params


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_params(self):
        engine = _make_engine_mock()
        cr = ContainerRunnable(engine=engine, poll_interval=0.01)
        result = cr.submit_pipeline_sync("pipe", params={})

        assert result.succeeded

    def test_none_params(self):
        engine = _make_engine_mock()
        cr = ContainerRunnable(engine=engine, poll_interval=0.01)
        result = cr.submit_pipeline_sync("pipe", params=None)

        assert result.succeeded

    def test_pipeline_name_with_dots(self):
        engine = _make_engine_mock()
        cr = ContainerRunnable(engine=engine)
        spec = cr._build_spec("finra.otc.transparency.ingest", None, None, None)

        assert spec.name == "pipeline-finra-otc-transparency-ingest"

    def test_image_resolver_returns_none_uses_default(self):
        engine = _make_engine_mock()
        cr = ContainerRunnable(engine=engine, image_resolver=lambda n: None)
        spec = cr._build_spec("pipe", None, None, None)

        assert spec.image == "spine-pipeline:latest"
