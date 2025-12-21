"""Tests for spine.mcp.server â€” MCP tool function coverage.

Tests the MCP tools by calling the underlying async functions directly
with a mocked AppContext / connection.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.mcp.server import AppContext, _get_version, create_server


class TestGetVersion:
    def test_returns_string(self):
        v = _get_version()
        assert isinstance(v, str)
        assert len(v) > 0

    def test_fallback_on_error(self):
        with patch.dict("sys.modules", {"spine": MagicMock(spec=[])}):
            v = _get_version()
            assert isinstance(v, str)
            assert v == "unknown"


class TestAppContext:
    def test_defaults(self):
        ctx = AppContext()
        assert ctx.conn is None
        assert ctx.initialized is False

    def test_with_connection(self):
        conn = MagicMock()
        ctx = AppContext(conn=conn, initialized=True)
        assert ctx.conn is conn
        assert ctx.initialized is True


class TestCreateServer:
    def test_returns_fastmcp(self):
        server = create_server()
        assert server is not None
        # The FastMCP object should have a name
        assert hasattr(server, "name") or hasattr(server, "_name")


class TestGetContext:
    """Test _get_context helper.

    Note: _get_context() does ``from spine.core.database import get_connection``
    inside its body.  spine.core.database does NOT export get_connection (it
    lives in spine.api.deps), so in practice _get_context always falls back to
    the uninitialized path unless the module is monkey-patched at runtime.
    """

    def test_returns_initialized_when_get_connection_available(self):
        """If get_connection were available, _get_context returns initialized ctx."""
        import spine.core.database as db_mod

        mock_conn = MagicMock()
        # Temporarily inject get_connection into the module
        db_mod.get_connection = MagicMock(return_value=mock_conn)
        try:
            from spine.mcp.server import _get_context
            ctx = _get_context()
            assert isinstance(ctx, AppContext)
            assert ctx.initialized is True
            assert ctx.conn is mock_conn
        finally:
            del db_mod.get_connection

    def test_returns_uninitialized_on_import_error(self):
        """Without get_connection in spine.core.database, falls back gracefully."""
        from spine.mcp.server import _get_context

        ctx = _get_context()
        assert isinstance(ctx, AppContext)
        assert ctx.initialized is False
        assert ctx.conn is None


# â”€â”€ MCP Tool Tests (async) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestHealthCheckTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_health_not_initialized(self, mock_ctx):
        from spine.mcp.server import health_check

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await health_check()
        assert result["status"] == "unhealthy"
        assert result["database"]["connected"] is False

    @pytest.mark.asyncio
    @patch("spine.ops.database.check_database_health")
    @patch("spine.mcp._app._get_context")
    async def test_health_healthy(self, mock_ctx, mock_check):
        from spine.mcp.server import health_check

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = MagicMock(
            connected=True,
            backend="sqlite",
            table_count=27,
            latency_ms=1.2,
        )
        mock_check.return_value = mock_result
        result = await health_check()
        assert result["status"] == "healthy"
        assert result["database"]["connected"] is True
        assert result["database"]["table_count"] == 27


class TestListRunsTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import list_runs

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await list_runs()
        assert result["runs"] == []
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.runs.list_runs")
    @patch("spine.mcp._app._get_context")
    async def test_returns_runs(self, mock_ctx, mock_list):
        from spine.mcp.server import list_runs

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        run = MagicMock()
        run.run_id = "run-1"
        run.workflow = "etl"
        run.status = "COMPLETED"
        run.started_at = None
        run.duration_ms = 100
        mock_result = MagicMock()
        mock_result.items = [run]
        mock_result.total = 1
        mock_list.return_value = mock_result
        result = await list_runs()
        assert len(result["runs"]) == 1
        assert result["runs"][0]["run_id"] == "run-1"


class TestSubmitRunTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import submit_run

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await submit_run(kind="workflow", name="etl")
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.runs.submit_run")
    @patch("spine.mcp._app._get_context")
    async def test_submit_success(self, mock_ctx, mock_submit):
        from spine.mcp.server import submit_run

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = MagicMock(run_id="new-run-1")
        mock_submit.return_value = mock_result
        result = await submit_run(kind="workflow", name="etl")
        assert result["submitted"] is True
        assert result["run_id"] == "new-run-1"


class TestCancelRunTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import cancel_run

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await cancel_run(run_id="run-1")
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.runs.cancel_run")
    @patch("spine.mcp._app._get_context")
    async def test_cancel_success(self, mock_ctx, mock_cancel):
        from spine.mcp.server import cancel_run

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_cancel.return_value = mock_result
        result = await cancel_run(run_id="run-1")
        assert result["cancelled"] is True


class TestListWorkflowsTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import list_workflows

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await list_workflows()
        assert result["workflows"] == []

    @pytest.mark.asyncio
    @patch("spine.ops.workflows.list_workflows")
    @patch("spine.mcp._app._get_context")
    async def test_returns_workflows(self, mock_ctx, mock_list):
        from spine.mcp.server import list_workflows

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        wf = MagicMock()
        wf.name = "daily_etl"
        wf.step_count = 3
        wf.description = "Daily ETL"
        mock_result = MagicMock()
        mock_result.items = [wf]
        mock_result.total = 1
        mock_list.return_value = mock_result
        result = await list_workflows()
        assert result["total"] == 1
        assert result["workflows"][0]["name"] == "daily_etl"


class TestListSchedulesTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import list_schedules

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await list_schedules()
        assert result["schedules"] == []

    @pytest.mark.asyncio
    @patch("spine.ops.schedules.list_schedules")
    @patch("spine.mcp._app._get_context")
    async def test_returns_schedules(self, mock_ctx, mock_list):
        from spine.mcp.server import list_schedules

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        sched = MagicMock()
        sched.schedule_id = "sched-1"
        sched.name = "hourly_check"
        sched.target_type = "workflow"
        sched.target_name = "health_check"
        sched.cron_expression = "0 * * * *"
        sched.enabled = True
        sched.next_run_at = None
        mock_result = MagicMock()
        mock_result.items = [sched]
        mock_result.total = 1
        mock_list.return_value = mock_result
        result = await list_schedules()
        assert result["total"] == 1
        assert result["schedules"][0]["name"] == "hourly_check"


class TestListAlertsTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import list_alerts

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await list_alerts()
        assert result["alerts"] == []

    @pytest.mark.asyncio
    @patch("spine.ops.alerts.list_alerts")
    @patch("spine.mcp._app._get_context")
    async def test_returns_alerts(self, mock_ctx, mock_list):
        from spine.mcp.server import list_alerts

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        alert = MagicMock()
        alert.id = "alert-1"
        alert.severity = "ERROR"
        alert.title = "Operation failed"
        alert.message = "ETL operation failed at step 2"
        alert.source = "worker"
        alert.created_at = "2024-01-01T00:00:00"
        mock_result = MagicMock()
        mock_result.items = [alert]
        mock_result.total = 1
        mock_list.return_value = mock_result
        result = await list_alerts()
        assert result["total"] == 1
        assert result["alerts"][0]["severity"] == "ERROR"


class TestListQualityResultsTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import list_quality_results

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await list_quality_results()
        assert result["results"] == []


class TestListAnomaliesTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import list_anomalies

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await list_anomalies()
        assert result["anomalies"] == []


class TestGetRunTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import get_run

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await get_run(run_id="run-1")
        assert "error" in result


class TestGetWorkflowTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import get_workflow

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await get_workflow(name="etl")
        assert "error" in result


class TestRunWorkflowTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import run_workflow

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await run_workflow(name="etl")
        assert "error" in result


class TestCreateScheduleTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import create_schedule

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await create_schedule(name="test", target_name="etl")
        assert "error" in result
