"""Tests for the SQLAlchemy ORM layer (base, tables, session)."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import DateTime, Integer, JSON, Text, create_engine, inspect, text
from sqlalchemy.orm import Session

from spine.core.orm.base import SpineBase, TimestampMixin
from spine.core.orm.session import (
    SAConnectionBridge,
    SpineSession,
    create_spine_engine,
    spine_session_factory,
)
from spine.core.orm.tables import (
    AlertChannelTable,
    AlertDeliveryTable,
    AlertTable,
    AlertThrottleTable,
    AnomalyTable,
    CalcDependencyTable,
    ConcurrencyLockTable,
    DataReadinessTable,
    DatabaseConnectionTable,
    DeadLetterTable,
    ExecutionEventTable,
    ExecutionTable,
    ExpectedScheduleTable,
    ManifestTable,
    MigrationTable,
    QualityTable,
    RejectTable,
    ScheduleLockTable,
    ScheduleRunTable,
    ScheduleTable,
    SourceCacheTable,
    SourceFetchTable,
    SourceTable,
    WorkItemTable,
    WorkflowEventTable,
    WorkflowRunTable,
    WorkflowStepTable,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def engine():
    """In-memory SQLite engine with all tables created."""
    eng = create_spine_engine("sqlite:///:memory:")
    SpineBase.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """SpineSession bound to the in-memory engine."""
    with SpineSession(bind=engine) as sess:
        yield sess


@pytest.fixture
def bridge(session):
    """SAConnectionBridge wrapping the test session."""
    return SAConnectionBridge(session)


# =========================================================================
# SpineBase — type_annotation_map
# =========================================================================


class TestSpineBase:
    """Verify the declarative base type_annotation_map."""

    def test_type_map_str(self):
        assert SpineBase.type_annotation_map[str] is Text

    def test_type_map_int(self):
        assert SpineBase.type_annotation_map[int] is Integer

    def test_type_map_bool(self):
        assert SpineBase.type_annotation_map[bool] is Integer

    def test_type_map_datetime(self):
        assert SpineBase.type_annotation_map[datetime.datetime] is DateTime

    def test_type_map_dict(self):
        assert SpineBase.type_annotation_map[dict] is JSON

    def test_type_map_list(self):
        assert SpineBase.type_annotation_map[list] is JSON


# =========================================================================
# TimestampMixin
# =========================================================================


class TestTimestampMixin:
    """Verify mixin columns exist and have correct attributes."""

    def test_created_at_exists(self):
        assert hasattr(TimestampMixin, "created_at")

    def test_updated_at_exists(self):
        assert hasattr(TimestampMixin, "updated_at")


# =========================================================================
# Tables — metadata
# =========================================================================

EXPECTED_TABLES = sorted([
    "_migrations",
    "core_alert_channels",
    "core_alert_deliveries",
    "core_alert_throttle",
    "core_alerts",
    "core_anomalies",
    "core_calc_dependencies",
    "core_concurrency_locks",
    "core_data_readiness",
    "core_database_connections",
    "core_dead_letters",
    "core_execution_events",
    "core_executions",
    "core_expected_schedules",
    "core_manifest",
    "core_quality",
    "core_rejects",
    "core_schedule_locks",
    "core_schedule_runs",
    "core_schedules",
    "core_source_cache",
    "core_source_fetches",
    "core_sources",
    "core_work_items",
    "core_workflow_events",
    "core_workflow_runs",
    "core_workflow_steps",
])


class TestTableMetadata:
    """Verify all 27 table classes are registered in SpineBase metadata."""

    def test_table_count(self):
        assert len(SpineBase.metadata.tables) == 27

    def test_table_names(self):
        actual = sorted(SpineBase.metadata.tables.keys())
        assert actual == EXPECTED_TABLES

    def test_create_all(self, engine):
        """create_all should succeed and produce exactly 27 tables."""
        insp = inspect(engine)
        actual = sorted(insp.get_table_names())
        assert actual == EXPECTED_TABLES


# =========================================================================
# Column type verification (spot-checks)
# =========================================================================


class TestColumnTypes:
    """Spot-check that ORM columns use correct SA types."""

    def test_execution_created_at_is_datetime(self):
        col = ExecutionTable.__table__.c["created_at"]
        assert isinstance(col.type, DateTime)

    def test_execution_params_is_json(self):
        col = ExecutionTable.__table__.c["params"]
        assert isinstance(col.type, JSON)

    def test_manifest_updated_at_is_datetime(self):
        col = ManifestTable.__table__.c["updated_at"]
        assert isinstance(col.type, DateTime)

    def test_anomaly_detected_at_is_datetime(self):
        col = AnomalyTable.__table__.c["detected_at"]
        assert isinstance(col.type, DateTime)

    def test_anomaly_details_json_is_json(self):
        col = AnomalyTable.__table__.c["details_json"]
        assert isinstance(col.type, JSON)

    def test_schedule_enabled_is_integer(self):
        """bool columns map to Integer for SQLite compatibility."""
        col = ScheduleTable.__table__.c["enabled"]
        assert isinstance(col.type, Integer)

    def test_source_enabled_is_integer(self):
        """bool columns map to Integer for SQLite compatibility."""
        col = SourceTable.__table__.c["enabled"]
        assert isinstance(col.type, Integer)

    def test_source_name_is_text(self):
        col = SourceTable.__table__.c["name"]
        assert isinstance(col.type, Text)


# =========================================================================
# ForeignKey spot-check
# =========================================================================


class TestForeignKeys:
    """Verify foreign key constraints."""

    def test_execution_event_fk(self):
        col = ExecutionEventTable.__table__.c["execution_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "core_executions.id"


# =========================================================================
# Server defaults (spot-check on a TimestampMixin table)
# =========================================================================


class TestServerDefaults:
    """Verify server_default is set for created_at/updated_at."""

    def test_anomaly_created_at_has_default(self):
        col = AnomalyTable.__table__.c["created_at"]
        assert col.server_default is not None

    def test_schedule_created_at_has_default(self):
        col = ScheduleTable.__table__.c["created_at"]
        assert col.server_default is not None

    def test_source_created_at_has_default(self):
        col = SourceTable.__table__.c["created_at"]
        assert col.server_default is not None

    def test_alert_created_at_has_default(self):
        col = AlertTable.__table__.c["created_at"]
        assert col.server_default is not None


# =========================================================================
# Engine factory
# =========================================================================


class TestCreateSpineEngine:
    """Tests for create_spine_engine()."""

    def test_returns_engine(self):
        eng = create_spine_engine("sqlite:///:memory:")
        from sqlalchemy.engine import Engine

        assert isinstance(eng, Engine)

    def test_sqlite_wal_mode(self):
        eng = create_spine_engine("sqlite:///:memory:")
        with eng.connect() as conn:
            result = conn.execute(text("PRAGMA journal_mode"))
            mode = result.scalar()
            # WAL for file-based, memory might return 'memory' or 'wal'
            assert mode in ("wal", "memory")

    def test_sqlite_foreign_keys_on(self):
        eng = create_spine_engine("sqlite:///:memory:")
        with eng.connect() as conn:
            result = conn.execute(text("PRAGMA foreign_keys"))
            assert result.scalar() == 1

    def test_echo_false_by_default(self):
        eng = create_spine_engine("sqlite:///:memory:")
        assert eng.echo is False

    def test_echo_true(self):
        eng = create_spine_engine("sqlite:///:memory:", echo=True)
        assert eng.echo is True


# =========================================================================
# SpineSession
# =========================================================================


class TestSpineSession:
    """Tests for SpineSession class."""

    def test_expire_on_commit_false(self, engine):
        with SpineSession(bind=engine) as sess:
            assert sess.expire_on_commit is False

    def test_is_session_subclass(self):
        assert issubclass(SpineSession, Session)

    def test_crud_roundtrip(self, engine):
        """Insert and read back a row via ORM."""
        SpineBase.metadata.create_all(engine)
        with SpineSession(bind=engine) as sess:
            src = SourceTable(
                id="test-src-1",
                name="unit-test-source",
                source_type="file",
                config_json={},
                enabled=True,
            )
            sess.add(src)
            sess.commit()

            loaded = sess.get(SourceTable, "test-src-1")
            assert loaded is not None
            assert loaded.name == "unit-test-source"


# =========================================================================
# spine_session_factory
# =========================================================================


class TestSessionFactory:
    """Tests for spine_session_factory()."""

    def test_returns_sessionmaker(self, engine):
        factory = spine_session_factory(engine)
        with factory() as sess:
            assert isinstance(sess, SpineSession)

    def test_factory_session_has_engine(self, engine):
        factory = spine_session_factory(engine)
        with factory() as sess:
            assert sess.bind is engine


# =========================================================================
# SAConnectionBridge
# =========================================================================


class TestSAConnectionBridge:
    """Tests for the SAConnectionBridge protocol adapter."""

    def test_has_session_property(self, bridge, session):
        assert bridge.session is session

    def test_execute_simple_select(self, bridge):
        bridge.execute("SELECT 1")
        result = bridge.fetchone()
        assert result == (1,)

    def test_execute_with_params(self, bridge, engine):
        SpineBase.metadata.create_all(engine)
        bridge.execute(
            "INSERT INTO core_sources (id, name, source_type, config_json, enabled) VALUES (?, ?, ?, ?, ?)",
            ["src-1", "bridge-test", "api", '{}', 1],
        )
        bridge.commit()
        bridge.execute("SELECT name FROM core_sources WHERE id = ?", ["src-1"])
        row = bridge.fetchone()
        assert row == ("bridge-test",)

    def test_fetchall(self, bridge, engine):
        SpineBase.metadata.create_all(engine)
        bridge.execute(
            "INSERT INTO core_sources (id, name, source_type, config_json, enabled) VALUES (?, ?, ?, ?, ?)",
            ["s1", "one", "file", '{}', 1],
        )
        bridge.execute(
            "INSERT INTO core_sources (id, name, source_type, config_json, enabled) VALUES (?, ?, ?, ?, ?)",
            ["s2", "two", "api", '{}', 1],
        )
        bridge.commit()
        bridge.execute("SELECT id FROM core_sources ORDER BY id")
        rows = bridge.fetchall()
        assert rows == [("s1",), ("s2",)]

    def test_fetchone_none_when_no_result(self, bridge):
        assert bridge.fetchone() is None

    def test_fetchall_empty_when_no_result(self, bridge):
        assert bridge.fetchall() == []

    def test_executemany(self, bridge, engine):
        SpineBase.metadata.create_all(engine)
        bridge.executemany(
            "INSERT INTO core_sources (id, name, source_type, config_json, enabled) VALUES (?, ?, ?, ?, ?)",
            [
                ["m1", "multi-1", "file", '{}', 1],
                ["m2", "multi-2", "api", '{}', 1],
            ],
        )
        bridge.commit()
        bridge.execute("SELECT COUNT(*) FROM core_sources")
        count = bridge.fetchone()
        assert count == (2,)

    def test_rollback(self, bridge, engine):
        SpineBase.metadata.create_all(engine)
        bridge.execute(
            "INSERT INTO core_sources (id, name, source_type, config_json, enabled) VALUES (?, ?, ?, ?, ?)",
            ["rb1", "rollback-test", "file", '{}', 1],
        )
        bridge.rollback()
        bridge.execute("SELECT COUNT(*) FROM core_sources")
        count = bridge.fetchone()
        assert count == (0,)

    def test_commit(self, bridge, engine):
        SpineBase.metadata.create_all(engine)
        bridge.execute(
            "INSERT INTO core_sources (id, name, source_type, config_json, enabled) VALUES (?, ?, ?, ?, ?)",
            ["c1", "commit-test", "file", '{}', 1],
        )
        bridge.commit()
        bridge.execute("SELECT COUNT(*) FROM core_sources")
        count = bridge.fetchone()
        assert count == (1,)


# =========================================================================
# Lazy import from spine.core
# =========================================================================


class TestLazyImport:
    """Verify that ORM symbols are accessible via spine.core lazy imports."""

    def test_import_orm_module(self):
        from spine.core import orm  # noqa: F811

        assert hasattr(orm, "SpineBase")
        assert hasattr(orm, "create_spine_engine")

    def test_import_spine_base(self):
        from spine.core import SpineBase as SB  # noqa: F811

        assert SB is SpineBase

    def test_import_timestamp_mixin(self):
        from spine.core import TimestampMixin as TM  # noqa: F811

        assert TM is TimestampMixin

    def test_import_create_spine_engine(self):
        from spine.core import create_spine_engine as cse  # noqa: F811

        assert cse is create_spine_engine

    def test_import_spine_session(self):
        from spine.core import SpineSession as SS  # noqa: F811

        assert SS is SpineSession

    def test_import_sa_connection_bridge(self):
        from spine.core import SAConnectionBridge as CB  # noqa: F811

        assert CB is SAConnectionBridge

    def test_import_spine_session_factory(self):
        from spine.core import spine_session_factory as sf  # noqa: F811

        assert sf is spine_session_factory


# =========================================================================
# ForeignKey completeness (30 FKs expected)
# =========================================================================


class TestForeignKeyCompleteness:
    """Verify all 28 ForeignKey constraints are present."""

    def test_total_fk_count(self):
        """28 FK constraints across all tables."""
        fk_count = sum(
            len(list(col.foreign_keys))
            for table in SpineBase.metadata.tables.values()
            for col in table.columns
        )
        assert fk_count == 28

    @pytest.mark.parametrize(
        "table_name,col_name,target",
        [
            ("core_executions", "parent_execution_id", "core_executions.id"),
            ("core_execution_events", "execution_id", "core_executions.id"),
            ("core_manifest", "execution_id", "core_executions.id"),
            ("core_rejects", "execution_id", "core_executions.id"),
            ("core_quality", "execution_id", "core_executions.id"),
            ("core_anomalies", "execution_id", "core_executions.id"),
            ("core_dead_letters", "execution_id", "core_executions.id"),
            ("core_concurrency_locks", "execution_id", "core_executions.id"),
            ("core_work_items", "current_execution_id", "core_executions.id"),
            ("core_work_items", "latest_execution_id", "core_executions.id"),
            ("core_workflow_runs", "parent_run_id", "core_workflow_runs.run_id"),
            ("core_workflow_runs", "schedule_id", "core_schedules.id"),
            ("core_workflow_steps", "run_id", "core_workflow_runs.run_id"),
            ("core_workflow_steps", "execution_id", "core_executions.id"),
            ("core_workflow_events", "run_id", "core_workflow_runs.run_id"),
            ("core_workflow_events", "step_id", "core_workflow_steps.step_id"),
            ("core_schedule_runs", "schedule_id", "core_schedules.id"),
            ("core_schedule_runs", "run_id", "core_workflow_runs.run_id"),
            ("core_schedule_runs", "execution_id", "core_executions.id"),
            ("core_schedule_locks", "schedule_id", "core_schedules.id"),
            ("core_alerts", "execution_id", "core_executions.id"),
            ("core_alerts", "run_id", "core_workflow_runs.run_id"),
            ("core_alert_deliveries", "alert_id", "core_alerts.id"),
            ("core_alert_deliveries", "channel_id", "core_alert_channels.id"),
            ("core_source_fetches", "source_id", "core_sources.id"),
            ("core_source_fetches", "execution_id", "core_executions.id"),
            ("core_source_fetches", "run_id", "core_workflow_runs.run_id"),
            ("core_source_cache", "source_id", "core_sources.id"),
        ],
    )
    def test_fk_target(self, table_name, col_name, target):
        col = SpineBase.metadata.tables[table_name].c[col_name]
        fks = list(col.foreign_keys)
        assert len(fks) == 1, f"Expected 1 FK on {table_name}.{col_name}"
        assert fks[0].target_fullname == target


# =========================================================================
# Relationships
# =========================================================================


class TestRelationships:
    """Verify ORM relationship() navigation works."""

    def test_execution_events_bidirectional(self, session, engine):
        SpineBase.metadata.create_all(engine)
        ex = ExecutionTable(
            id="ex1", workflow="test", lane="default",
            trigger_source="api", status="running",
            created_at=datetime.datetime.now(), retry_count=0,
        )
        session.add(ex)
        ev = ExecutionEventTable(
            id="ev1", execution_id="ex1",
            event_type="started",
            timestamp=datetime.datetime.now(),
        )
        session.add(ev)
        session.commit()

        loaded = session.get(ExecutionTable, "ex1")
        assert len(loaded.events) == 1
        assert loaded.events[0].execution.id == "ex1"

    def test_execution_parent_self_ref(self, session, engine):
        SpineBase.metadata.create_all(engine)
        parent = ExecutionTable(
            id="p1", workflow="t", lane="default",
            trigger_source="api", status="done",
            created_at=datetime.datetime.now(), retry_count=0,
        )
        child = ExecutionTable(
            id="c1", workflow="t", lane="default",
            trigger_source="api", status="done",
            created_at=datetime.datetime.now(), retry_count=0,
            parent_execution_id="p1",
        )
        session.add_all([parent, child])
        session.commit()
        assert session.get(ExecutionTable, "c1").parent.id == "p1"

    def test_schedule_runs_and_lock(self, session, engine):
        SpineBase.metadata.create_all(engine)
        sch = ScheduleTable(
            id="sch1", name="daily", target_name="ingest",
            schedule_type="cron", timezone="UTC", enabled=True,
            max_instances=1, misfire_grace_seconds=60, version=1,
        )
        session.add(sch)
        sr = ScheduleRunTable(
            id="sr1", schedule_id="sch1", schedule_name="daily",
            scheduled_at=datetime.datetime.now(),
        )
        session.add(sr)
        sl = ScheduleLockTable(
            schedule_id="sch1", locked_by="w1",
            locked_at=datetime.datetime.now(),
            expires_at=datetime.datetime.now(),
        )
        session.add(sl)
        session.commit()

        loaded = session.get(ScheduleTable, "sch1")
        assert len(loaded.runs) == 1
        assert loaded.lock is not None

    def test_source_fetches_and_cache(self, session, engine):
        SpineBase.metadata.create_all(engine)
        src = SourceTable(
            id="src1", name="feed", source_type="api",
            config_json={}, enabled=True,
        )
        session.add(src)
        sf = SourceFetchTable(
            id="sf1", source_id="src1", source_name="feed",
            source_type="api", source_locator="http://x",
            status="ok", started_at=datetime.datetime.now(),
        )
        session.add(sf)
        session.commit()
        assert len(session.get(SourceTable, "src1").fetches) == 1

    def test_alert_deliveries(self, session, engine):
        SpineBase.metadata.create_all(engine)
        ch = AlertChannelTable(
            id="ch1", name="slack", channel_type="slack",
            config_json={}, enabled=True, throttle_minutes=5,
            consecutive_failures=0,
        )
        session.add(ch)
        al = AlertTable(
            id="al1", severity="ERROR", title="Fail",
            message="msg", source="test",
        )
        session.add(al)
        ad = AlertDeliveryTable(
            id="ad1", alert_id="al1", channel_id="ch1",
            channel_name="slack", attempt=1,
        )
        session.add(ad)
        session.commit()
        assert len(session.get(AlertTable, "al1").deliveries) == 1

    def test_workflow_run_steps_and_events(self, session, engine):
        SpineBase.metadata.create_all(engine)
        wr = WorkflowRunTable(
            run_id="wr1", workflow_name="test", domain="d",
            status="RUNNING", triggered_by="api",
        )
        session.add(wr)
        ws = WorkflowStepTable(
            step_id="ws1", run_id="wr1", step_name="s1",
            step_type="operation", step_order=1,
        )
        session.add(ws)
        we = WorkflowEventTable(run_id="wr1", event_type="started")
        session.add(we)
        session.commit()

        loaded = session.get(WorkflowRunTable, "wr1")
        assert len(loaded.steps) == 1
        assert len(loaded.events) == 1


# =========================================================================
# BaseRepository.from_session() bridge
# =========================================================================


class TestRepositoryBridge:
    """Tests for BaseRepository.from_session()."""

    def test_insert_and_query(self, session, engine):
        from spine.core.repository import BaseRepository

        SpineBase.metadata.create_all(engine)
        repo = BaseRepository.from_session(session)
        repo.insert("core_sources", {
            "id": "s1", "name": "test", "source_type": "api",
            "config_json": "{}", "enabled": 1,
        })
        repo.commit()
        rows = repo.query("SELECT id, name FROM core_sources")
        assert len(rows) == 1
        assert rows[0]["id"] == "s1"

    def test_query_one(self, session, engine):
        from spine.core.repository import BaseRepository

        SpineBase.metadata.create_all(engine)
        repo = BaseRepository.from_session(session)
        repo.insert("core_sources", {
            "id": "s1", "name": "test", "source_type": "api",
            "config_json": "{}", "enabled": 1,
        })
        repo.commit()
        row = repo.query_one(
            "SELECT name FROM core_sources WHERE id = ?", ("s1",)
        )
        assert row is not None
        assert row["name"] == "test"

    def test_insert_many(self, session, engine):
        from spine.core.repository import BaseRepository

        SpineBase.metadata.create_all(engine)
        repo = BaseRepository.from_session(session)
        count = repo.insert_many("core_sources", [
            {"id": "s1", "name": "one", "source_type": "api", "config_json": "{}", "enabled": 1},
            {"id": "s2", "name": "two", "source_type": "file", "config_json": "{}", "enabled": 0},
        ])
        repo.commit()
        assert count == 2
        rows = repo.query("SELECT id FROM core_sources ORDER BY id")
        assert len(rows) == 2


# =========================================================================
# SAConnectionBridge.description property
# =========================================================================


class TestBridgeDescription:
    """Verify the description property for DB-API 2.0 compat."""

    def test_description_after_select(self, bridge, engine):
        SpineBase.metadata.create_all(engine)
        bridge.execute("SELECT 1 AS val, 'hello' AS msg")
        desc = bridge.description
        assert desc is not None
        assert desc[0][0] == "val"
        assert desc[1][0] == "msg"

    def test_description_none_before_execute(self):
        """Before any execute, description is None."""
        eng = create_spine_engine("sqlite:///:memory:")
        with SpineSession(bind=eng) as sess:
            b = SAConnectionBridge(sess)
            assert b.description is None