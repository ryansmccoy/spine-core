"""Tests for spine.ops.runs — run operations."""

from spine.ops.database import initialize_database
from spine.ops.runs import cancel_run, get_run, list_runs, retry_run
from spine.ops.requests import (
    CancelRunRequest,
    GetRunRequest,
    ListRunsRequest,
    RetryRunRequest,
)


class TestListRuns:
    def test_empty(self, ctx):
        initialize_database(ctx)
        result = list_runs(ctx, ListRunsRequest())
        assert result.success is True
        assert result.data == []
        assert result.total == 0

    def test_with_data(self, ctx):
        initialize_database(ctx)
        # Insert a fake execution row
        ctx.conn.execute(
            "INSERT INTO core_executions (id, workflow, status, created_at, started_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            ("run-1", "test.pipe", "completed"),
        )
        ctx.conn.commit()

        result = list_runs(ctx, ListRunsRequest())
        assert result.success is True
        assert result.total == 1
        assert len(result.data) == 1
        assert result.data[0].run_id == "run-1"

    def test_filter_by_status(self, ctx):
        initialize_database(ctx)
        ctx.conn.execute(
            "INSERT INTO core_executions (id, workflow, status, created_at, started_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            ("r1", "p", "completed"),
        )
        ctx.conn.execute(
            "INSERT INTO core_executions (id, workflow, status, created_at, started_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            ("r2", "p", "failed"),
        )
        ctx.conn.commit()

        result = list_runs(ctx, ListRunsRequest(status="failed"))
        assert result.success is True
        assert result.total == 1

    def test_pagination(self, ctx):
        initialize_database(ctx)
        for i in range(5):
            ctx.conn.execute(
                "INSERT INTO core_executions (id, workflow, status, created_at, started_at) "
                "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
                (f"r{i}", "p", "completed"),
            )
        ctx.conn.commit()

        result = list_runs(ctx, ListRunsRequest(limit=2, offset=0))
        assert result.total == 5
        assert len(result.data) == 2
        assert result.has_more is True


class TestGetRun:
    def test_not_found(self, ctx):
        initialize_database(ctx)
        result = get_run(ctx, GetRunRequest(run_id="nonexistent"))
        assert result.success is False
        assert result.error.code == "NOT_FOUND"

    def test_found(self, ctx):
        initialize_database(ctx)
        ctx.conn.execute(
            "INSERT INTO core_executions (id, workflow, status, created_at, started_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            ("run-x", "test.pipe", "running"),
        )
        ctx.conn.commit()

        result = get_run(ctx, GetRunRequest(run_id="run-x"))
        assert result.success is True
        assert result.data.run_id == "run-x"
        assert result.data.status == "running"

    def test_validation_empty_id(self, ctx):
        result = get_run(ctx, GetRunRequest(run_id=""))
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"


class TestCancelRun:
    def test_cancel_running(self, ctx):
        initialize_database(ctx)
        ctx.conn.execute(
            "INSERT INTO core_executions (id, workflow, status, created_at, started_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            ("run-c", "p", "running"),
        )
        ctx.conn.commit()

        result = cancel_run(ctx, CancelRunRequest(run_id="run-c"))
        assert result.success is True

    def test_cancel_completed_fails(self, ctx):
        initialize_database(ctx)
        ctx.conn.execute(
            "INSERT INTO core_executions (id, workflow, status, created_at, started_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            ("run-d", "p", "completed"),
        )
        ctx.conn.commit()

        result = cancel_run(ctx, CancelRunRequest(run_id="run-d"))
        assert result.success is False
        assert result.error.code == "NOT_CANCELLABLE"

    def test_cancel_dry_run(self, dry_ctx):
        result = cancel_run(dry_ctx, CancelRunRequest(run_id="any"))
        assert result.success is True


class TestRetryRun:
    def test_retry_failed(self, ctx):
        initialize_database(ctx)
        ctx.conn.execute(
            "INSERT INTO core_executions (id, workflow, status, created_at, started_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            ("run-f", "p", "failed"),
        )
        ctx.conn.commit()

        result = retry_run(ctx, RetryRunRequest(run_id="run-f"))
        assert result.success is True
        assert result.data.would_execute is True

    def test_retry_running_fails(self, ctx):
        initialize_database(ctx)
        ctx.conn.execute(
            "INSERT INTO core_executions (id, workflow, status, created_at, started_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            ("run-r", "p", "running"),
        )
        ctx.conn.commit()

        result = retry_run(ctx, RetryRunRequest(run_id="run-r"))
        assert result.success is False
        assert result.error.code == "VALIDATION_FAILED"

    def test_retry_dry_run(self, dry_ctx):
        result = retry_run(dry_ctx, RetryRunRequest(run_id="any"))
        assert result.success is True
        assert result.data.dry_run is True
