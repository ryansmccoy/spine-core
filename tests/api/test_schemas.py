"""
Tests for API schemas — common envelopes + domain schemas.
"""

from __future__ import annotations

import pytest

from spine.api.schemas.common import (
    ErrorDetail,
    Link,
    PageMeta,
    PagedResponse,
    ProblemDetail,
    SuccessResponse,
)
from spine.api.schemas.domains import (
    AnomalySchema,
    CapabilitiesSchema,
    DatabaseHealthSchema,
    DatabaseInitSchema,
    DeadLetterSchema,
    HealthStatusSchema,
    PurgeResultSchema,
    QualityResultSchema,
    RunAcceptedSchema,
    RunDetailSchema,
    RunSummarySchema,
    ScheduleDetailSchema,
    ScheduleSummarySchema,
    TableCountSchema,
    WorkflowDetailSchema,
    WorkflowSummarySchema,
)


# ── Common schemas ───────────────────────────────────────────────────────


class TestLink:
    def test_defaults(self):
        link = Link(rel="self", href="/api/v1/thing")
        assert link.method == "GET"

    def test_custom_method(self):
        link = Link(rel="create", href="/api/v1/thing", method="POST")
        assert link.method == "POST"


class TestProblemDetail:
    def test_defaults(self):
        pd = ProblemDetail(title="Not found", status=404)
        assert pd.type == "about:blank"
        assert pd.detail == ""
        assert pd.errors == []

    def test_with_errors(self):
        pd = ProblemDetail(
            title="Validation error",
            status=400,
            errors=[ErrorDetail(code="REQUIRED", message="field is required", field="name")],
        )
        assert len(pd.errors) == 1
        assert pd.errors[0].field == "name"

    def test_serialisation(self):
        pd = ProblemDetail(title="test", status=500, detail="boom")
        d = pd.model_dump()
        assert d["status"] == 500
        assert d["detail"] == "boom"


class TestPageMeta:
    def test_basic(self):
        pm = PageMeta(total=100, limit=50, offset=0, has_more=True)
        assert pm.has_more is True
        assert pm.total == 100


class TestSuccessResponse:
    def test_simple(self):
        r = SuccessResponse(data={"msg": "ok"}, elapsed_ms=1.5)
        assert r.data == {"msg": "ok"}
        assert r.warnings == []
        assert r.links == []

    def test_with_warnings(self):
        r = SuccessResponse(data="x", warnings=["beware"])
        assert r.warnings == ["beware"]


class TestPagedResponse:
    def test_basic(self):
        pr = PagedResponse(
            data=[1, 2, 3],
            page=PageMeta(total=3, limit=50, offset=0, has_more=False),
        )
        assert len(pr.data) == 3
        assert pr.page.total == 3


# ── Domain schemas ───────────────────────────────────────────────────────


class TestDatabaseSchemas:
    def test_init(self):
        s = DatabaseInitSchema(tables_created=["a", "b"])
        assert len(s.tables_created) == 2

    def test_table_count(self):
        s = TableCountSchema(table="runs", count=42)
        assert s.count == 42

    def test_purge(self):
        s = PurgeResultSchema(rows_deleted=10, tables_purged=["runs"])
        assert s.rows_deleted == 10

    def test_health(self):
        s = DatabaseHealthSchema(connected=True, backend="sqlite")
        assert s.connected is True


class TestWorkflowSchemas:
    def test_summary(self):
        s = WorkflowSummarySchema(name="etl", step_count=3)
        assert s.step_count == 3

    def test_detail(self):
        s = WorkflowDetailSchema(name="etl")
        assert s.steps == []
        assert s.metadata == {}


class TestRunSchemas:
    def test_summary(self):
        s = RunSummarySchema(run_id="r-1", status="running")
        assert s.run_id == "r-1"

    def test_detail_inherits(self):
        s = RunDetailSchema(run_id="r-2", status="failed", error="boom")
        assert s.error == "boom"
        assert s.params == {}

    def test_accepted(self):
        s = RunAcceptedSchema(run_id="r-3", dry_run=True)
        assert s.dry_run is True


class TestScheduleSchemas:
    def test_summary(self):
        s = ScheduleSummarySchema(schedule_id="s-1", name="etl", target_type="workflow", target_name="etl")
        assert s.enabled is True

    def test_detail_inherits(self):
        s = ScheduleDetailSchema(schedule_id="s-2", name="etl", target_type="workflow", target_name="etl", version=1)
        assert s.version == 1


class TestDLQSchema:
    def test_basic(self):
        s = DeadLetterSchema(id="dl-1", workflow="ingest", error="timeout")
        assert s.replay_count == 0


class TestQualitySchema:
    def test_basic(self):
        s = QualityResultSchema(workflow="etl", score=0.95)
        assert s.score == 0.95


class TestAnomalySchema:
    def test_basic(self):
        s = AnomalySchema(id="a-1", severity="high", value=100.0, threshold=50.0)
        assert s.value > s.threshold


class TestHealthSchemas:
    def test_health_status(self):
        s = HealthStatusSchema(status="healthy", version="0.3.0")
        assert s.status == "healthy"

    def test_capabilities(self):
        s = CapabilitiesSchema(tier="full", scheduling=True)
        assert s.scheduling is True
