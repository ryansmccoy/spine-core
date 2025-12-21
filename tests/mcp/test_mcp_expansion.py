"""Tests for 16 new MCP tools added in Sprint 2 expansion (13→29).

Tests the MCP tools by calling the underlying async functions directly
with a mocked AppContext / connection.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spine.mcp.server import AppContext


# ── Runs: retry_run ─────────────────────────────────────────────────


class TestRetryRunTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import retry_run

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await retry_run(run_id="run-1")
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.runs.retry_run")
    @patch("spine.mcp._app._get_context")
    async def test_retry_success(self, mock_ctx, mock_retry):
        from spine.mcp.server import retry_run

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = MagicMock(run_id="run-1")
        mock_retry.return_value = mock_result
        result = await retry_run(run_id="run-1")
        assert result["retried"] is True
        assert result["run_id"] == "run-1"

    @pytest.mark.asyncio
    @patch("spine.ops.runs.retry_run")
    @patch("spine.mcp._app._get_context")
    async def test_retry_failure(self, mock_ctx, mock_retry):
        from spine.mcp.server import retry_run

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Run is not in failed status"
        mock_retry.return_value = mock_result
        result = await retry_run(run_id="run-1")
        assert "error" in result
        assert "failed" in result["error"].lower()


# ── Runs: get_run_events ────────────────────────────────────────────


class TestGetRunEventsTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import get_run_events

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await get_run_events(run_id="run-1")
        assert result["events"] == []
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.runs.get_run_events")
    @patch("spine.mcp._app._get_context")
    async def test_returns_events(self, mock_ctx, mock_events):
        from spine.mcp.server import get_run_events

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        event = MagicMock()
        event.event_id = "ev-1"
        event.event_type = "submitted"
        event.timestamp = "2024-01-01T00:00:00"
        event.message = "Run submitted"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.items = [event]
        mock_result.total = 1
        mock_events.return_value = mock_result
        result = await get_run_events(run_id="run-1")
        assert len(result["events"]) == 1
        assert result["events"][0]["event_type"] == "submitted"
        assert result["total"] == 1

    @pytest.mark.asyncio
    @patch("spine.ops.runs.get_run_events")
    @patch("spine.mcp._app._get_context")
    async def test_respects_limit(self, mock_ctx, mock_events):
        from spine.mcp.server import get_run_events

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.items = []
        mock_result.total = 0
        mock_events.return_value = mock_result
        await get_run_events(run_id="run-1", limit=1000)
        # Verify the limit was capped at 500
        call_args = mock_events.call_args
        request = call_args[0][1]  # second positional arg
        assert request.limit == 500


# ── Runs: get_run_steps ─────────────────────────────────────────────


class TestGetRunStepsTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import get_run_steps

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await get_run_steps(run_id="run-1")
        assert result["steps"] == []
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.runs.get_run_steps")
    @patch("spine.mcp._app._get_context")
    async def test_returns_steps(self, mock_ctx, mock_steps):
        from spine.mcp.server import get_run_steps

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        step = MagicMock()
        step.step_id = "step-1"
        step.step_name = "extract"
        step.step_type = "operation"
        step.status = "COMPLETED"
        step.started_at = "2024-01-01T00:00:00"
        step.completed_at = "2024-01-01T00:01:00"
        step.duration_ms = 60000
        step.attempt = 1
        step.error = None
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.items = [step]
        mock_result.total = 1
        mock_steps.return_value = mock_result
        result = await get_run_steps(run_id="run-1")
        assert len(result["steps"]) == 1
        assert result["steps"][0]["step_name"] == "extract"
        assert result["steps"][0]["status"] == "COMPLETED"


# ── Runs: get_run_logs ──────────────────────────────────────────────


class TestGetRunLogsTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import get_run_logs

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await get_run_logs(run_id="run-1")
        assert result["logs"] == []
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.runs.get_run_logs")
    @patch("spine.mcp._app._get_context")
    async def test_returns_logs(self, mock_ctx, mock_logs):
        from spine.mcp.server import get_run_logs

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        entry = MagicMock()
        entry.timestamp = "2024-01-01T00:00:00"
        entry.level = "INFO"
        entry.message = "Starting ETL"
        entry.step_name = "extract"
        entry.logger = "spine.etl"
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.items = [entry]
        mock_result.total = 1
        mock_logs.return_value = mock_result
        result = await get_run_logs(run_id="run-1")
        assert len(result["logs"]) == 1
        assert result["logs"][0]["level"] == "INFO"
        assert result["logs"][0]["message"] == "Starting ETL"

    @pytest.mark.asyncio
    @patch("spine.ops.runs.get_run_logs")
    @patch("spine.mcp._app._get_context")
    async def test_passes_filters(self, mock_ctx, mock_logs):
        from spine.mcp.server import get_run_logs

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.items = []
        mock_result.total = 0
        mock_logs.return_value = mock_result
        await get_run_logs(run_id="run-1", step="extract", level="ERROR")
        call_args = mock_logs.call_args
        request = call_args[0][1]
        assert request.step == "extract"
        assert request.level == "ERROR"


# ── Schedules: get_schedule ─────────────────────────────────────────


class TestGetScheduleTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import get_schedule

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await get_schedule(schedule_id="sched-1")
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.schedules.get_schedule")
    @patch("spine.mcp._app._get_context")
    async def test_returns_schedule(self, mock_ctx, mock_get):
        from spine.mcp.server import get_schedule

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        sched_data = MagicMock()
        sched_data.schedule_id = "sched-1"
        sched_data.configure_mock(name="hourly_check")
        sched_data.target_type = "workflow"
        sched_data.target_name = "health_check"
        sched_data.cron_expression = "0 * * * *"
        sched_data.interval_seconds = None
        sched_data.enabled = True
        mock_result.data = sched_data
        mock_get.return_value = mock_result
        result = await get_schedule(schedule_id="sched-1")
        assert result["schedule_id"] == "sched-1"
        assert result["name"] == "hourly_check"
        assert result["enabled"] is True


# ── Schedules: update_schedule ──────────────────────────────────────


class TestUpdateScheduleTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import update_schedule

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await update_schedule(schedule_id="sched-1", enabled=False)
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.schedules.update_schedule")
    @patch("spine.mcp._app._get_context")
    async def test_update_success(self, mock_ctx, mock_update):
        from spine.mcp.server import update_schedule

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = MagicMock(
            schedule_id="sched-1",
            name="hourly_check",
            target_type="workflow",
            target_name="health_check",
            cron_expression="0 * * * *",
            interval_seconds=None,
            enabled=False,
        )
        mock_update.return_value = mock_result
        result = await update_schedule(schedule_id="sched-1", enabled=False)
        assert result["updated"] is True
        assert result["enabled"] is False


# ── Schedules: delete_schedule ──────────────────────────────────────


class TestDeleteScheduleTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import delete_schedule

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await delete_schedule(schedule_id="sched-1")
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.schedules.delete_schedule")
    @patch("spine.mcp._app._get_context")
    async def test_delete_success(self, mock_ctx, mock_delete):
        from spine.mcp.server import delete_schedule

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_delete.return_value = mock_result
        result = await delete_schedule(schedule_id="sched-1")
        assert result["deleted"] is True
        assert result["schedule_id"] == "sched-1"


# ── Monitoring: list_alert_channels ─────────────────────────────────


class TestListAlertChannelsTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import list_alert_channels

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await list_alert_channels()
        assert result["channels"] == []
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.alerts.list_alert_channels")
    @patch("spine.mcp._app._get_context")
    async def test_returns_channels(self, mock_ctx, mock_list):
        from spine.mcp.server import list_alert_channels

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        ch = MagicMock()
        ch.id = "ch-1"
        ch.name = "ops-slack"
        ch.channel_type = "slack"
        ch.min_severity = "ERROR"
        ch.enabled = True
        ch.consecutive_failures = 0
        mock_result = MagicMock()
        mock_result.items = [ch]
        mock_result.total = 1
        mock_list.return_value = mock_result
        result = await list_alert_channels()
        assert len(result["channels"]) == 1
        assert result["channels"][0]["name"] == "ops-slack"
        assert result["total"] == 1


# ── Monitoring: create_alert_channel ────────────────────────────────


class TestCreateAlertChannelTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import create_alert_channel

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await create_alert_channel(name="test")
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.alerts.create_alert_channel")
    @patch("spine.mcp._app._get_context")
    async def test_create_success(self, mock_ctx, mock_create):
        from spine.mcp.server import create_alert_channel

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {"id": "ch-1", "name": "ops-slack", "created": True}
        mock_create.return_value = mock_result
        result = await create_alert_channel(name="ops-slack", channel_type="slack")
        assert result["created"] is True
        assert result["id"] == "ch-1"


# ── Monitoring: acknowledge_alert ───────────────────────────────────


class TestAcknowledgeAlertTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import acknowledge_alert

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await acknowledge_alert(alert_id="alert-1")
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.alerts.acknowledge_alert")
    @patch("spine.mcp._app._get_context")
    async def test_acknowledge_success(self, mock_ctx, mock_ack):
        from spine.mcp.server import acknowledge_alert

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {"id": "alert-1", "acknowledged": True}
        mock_ack.return_value = mock_result
        result = await acknowledge_alert(alert_id="alert-1", acknowledged_by="ryan")
        assert result["acknowledged"] is True

    @pytest.mark.asyncio
    @patch("spine.ops.alerts.acknowledge_alert")
    @patch("spine.mcp._app._get_context")
    async def test_acknowledge_not_found(self, mock_ctx, mock_ack):
        from spine.mcp.server import acknowledge_alert

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Alert 'alert-1' not found"
        mock_ack.return_value = mock_result
        result = await acknowledge_alert(alert_id="alert-1")
        assert "error" in result


# ── Health: get_capabilities ────────────────────────────────────────


class TestGetCapabilitiesTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import get_capabilities

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await get_capabilities()
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.health.get_capabilities")
    @patch("spine.mcp._app._get_context")
    async def test_returns_capabilities(self, mock_ctx, mock_caps):
        from spine.mcp.server import get_capabilities

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = MagicMock(
            tier="standard",
            sync_execution=True,
            async_execution=True,
            scheduling=True,
            rate_limiting=True,
            execution_history=True,
            dlq=True,
        )
        mock_caps.return_value = mock_result
        result = await get_capabilities()
        assert result["tier"] == "standard"
        assert result["scheduling"] is True
        assert result["dlq"] is True


# ── Sources: list_sources ───────────────────────────────────────────


class TestListSourcesTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import list_sources

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await list_sources()
        assert result["sources"] == []
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.sources.list_sources")
    @patch("spine.mcp._app._get_context")
    async def test_returns_sources(self, mock_ctx, mock_list):
        from spine.mcp.server import list_sources

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        src = MagicMock()
        src.id = "src-1"
        src.name = "yahoo_finance"
        src.source_type = "http"
        src.domain = "market_data"
        src.enabled = True
        src.created_at = None
        mock_result = MagicMock()
        mock_result.items = [src]
        mock_result.total = 1
        mock_list.return_value = mock_result
        result = await list_sources()
        assert len(result["sources"]) == 1
        assert result["sources"][0]["name"] == "yahoo_finance"
        assert result["total"] == 1


# ── Sources: get_source ─────────────────────────────────────────────


class TestGetSourceTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import get_source

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await get_source(source_id="src-1")
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.sources.get_source")
    @patch("spine.mcp._app._get_context")
    async def test_returns_source(self, mock_ctx, mock_get):
        from spine.mcp.server import get_source

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = MagicMock(
            id="src-1",
            name="yahoo_finance",
            source_type="http",
            domain="market_data",
            enabled=True,
            config={"url": "https://example.com"},
            created_at=None,
            updated_at=None,
        )
        mock_get.return_value = mock_result
        result = await get_source(source_id="src-1")
        assert result["id"] == "src-1"
        assert result["source_type"] == "http"

    @pytest.mark.asyncio
    @patch("spine.ops.sources.get_source")
    @patch("spine.mcp._app._get_context")
    async def test_not_found(self, mock_ctx, mock_get):
        from spine.mcp.server import get_source

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Source 'src-1' not found"
        mock_get.return_value = mock_result
        result = await get_source(source_id="src-1")
        assert "error" in result


# ── Sources: register_source ────────────────────────────────────────


class TestRegisterSourceTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import register_source

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await register_source(name="test")
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.sources.register_source")
    @patch("spine.mcp._app._get_context")
    async def test_register_success(self, mock_ctx, mock_register):
        from spine.mcp.server import register_source

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {"id": "src-1", "name": "yahoo_finance", "created": True}
        mock_register.return_value = mock_result
        result = await register_source(
            name="yahoo_finance",
            source_type="http",
            config={"url": "https://example.com"},
            domain="market_data",
        )
        assert result["created"] is True
        assert result["id"] == "src-1"


# ── DLQ: list_dead_letters ──────────────────────────────────────────


class TestListDeadLettersTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import list_dead_letters

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await list_dead_letters()
        assert result["dead_letters"] == []
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.dlq.list_dead_letters")
    @patch("spine.mcp._app._get_context")
    async def test_returns_dead_letters(self, mock_ctx, mock_list):
        from spine.mcp.server import list_dead_letters

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        dl = MagicMock()
        dl.id = "dl-1"
        dl.workflow = "daily_etl"
        dl.error = "Connection timeout"
        dl.created_at = "2024-01-01T00:00:00"
        dl.replay_count = 0
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.items = [dl]
        mock_result.total = 1
        mock_list.return_value = mock_result
        result = await list_dead_letters()
        assert len(result["dead_letters"]) == 1
        assert result["dead_letters"][0]["workflow"] == "daily_etl"
        assert result["total"] == 1


# ── DLQ: replay_dead_letter ─────────────────────────────────────────


class TestReplayDeadLetterTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import replay_dead_letter

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await replay_dead_letter(dead_letter_id="dl-1")
        assert "error" in result

    @pytest.mark.asyncio
    @patch("spine.ops.dlq.replay_dead_letter")
    @patch("spine.mcp._app._get_context")
    async def test_replay_success(self, mock_ctx, mock_replay):
        from spine.mcp.server import replay_dead_letter

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = True
        mock_replay.return_value = mock_result
        result = await replay_dead_letter(dead_letter_id="dl-1")
        assert result["replayed"] is True
        assert result["dead_letter_id"] == "dl-1"

    @pytest.mark.asyncio
    @patch("spine.ops.dlq.replay_dead_letter")
    @patch("spine.mcp._app._get_context")
    async def test_replay_not_found(self, mock_ctx, mock_replay):
        from spine.mcp.server import replay_dead_letter

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Dead letter 'dl-1' not found"
        mock_replay.return_value = mock_result
        result = await replay_dead_letter(dead_letter_id="dl-1")
        assert "error" in result


# ── Stats: get_run_stats ────────────────────────────────────────────


class TestGetRunStatsTool:
    @pytest.mark.asyncio
    @patch("spine.mcp._app._get_context")
    async def test_not_initialized(self, mock_ctx):
        from spine.mcp.server import get_run_stats

        mock_ctx.return_value = AppContext(conn=None, initialized=False)
        result = await get_run_stats()
        assert "error" in result
        assert result["total"] == 0

    @pytest.mark.asyncio
    @patch("spine.ops.stats.get_run_stats")
    @patch("spine.mcp._app._get_context")
    async def test_returns_stats(self, mock_ctx, mock_stats):
        from spine.mcp.server import get_run_stats

        conn = MagicMock()
        mock_ctx.return_value = AppContext(conn=conn, initialized=True)
        mock_stats.return_value = {
            "completed": 42,
            "failed": 3,
            "running": 1,
            "pending": 5,
            "total": 51,
        }
        result = await get_run_stats()
        assert result["total"] == 51
        assert result["completed"] == 42
        assert result["failed"] == 3
