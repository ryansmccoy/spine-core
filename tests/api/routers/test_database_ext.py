"""Tests for database router helper functions and endpoints.

Covers _mask_url, _detect_tier, _get_sqlite_file_path, _get_file_size_mb,
and the /config, /schema, /query, /vacuum, /backup endpoints.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from spine.api.routers.database import (
    _detect_tier,
    _get_file_size_mb,
    _get_sqlite_file_path,
    _mask_url,
    router,
)


# ── Pure function tests ──────────────────────────────────────


class TestMaskUrl:
    def test_mask_postgres_password(self):
        url = "postgresql://user:secret@host:5432/db"
        assert _mask_url(url) == "postgresql://user:***@host:5432/db"

    def test_no_password(self):
        url = "postgresql://user@host:5432/db"
        assert _mask_url(url) == "postgresql://user@host:5432/db"

    def test_sqlite_url_unchanged(self):
        url = "sqlite:///path/to/db.sqlite"
        assert _mask_url(url) == "sqlite:///path/to/db.sqlite"

    def test_no_scheme(self):
        assert _mask_url("just-a-path") == "just-a-path"

    def test_malformed_url(self):
        result = _mask_url("weird://")
        assert "://" in result


class TestDetectTier:
    def test_explicit_tier_env(self):
        with patch.dict(os.environ, {"SPINE_TIER": "full"}, clear=False):
            tier, hint = _detect_tier()
            assert tier == "full"
            assert hint == ".env.full"

    def test_postgres_url(self):
        with patch.dict(os.environ, {"SPINE_TIER": "", "SPINE_DATABASE_URL": "postgresql://host/db"}, clear=False):
            tier, hint = _detect_tier()
            assert tier == "standard"

    def test_timescale_url(self):
        with patch.dict(os.environ, {"SPINE_TIER": "", "SPINE_DATABASE_URL": "postgresql://localhost/timescaledb"}, clear=False):
            tier, hint = _detect_tier()
            assert tier == "full"

    def test_default_minimal(self):
        with patch.dict(os.environ, {"SPINE_TIER": "", "SPINE_DATABASE_URL": "sqlite:///test.db"}, clear=False):
            tier, hint = _detect_tier()
            assert tier == "minimal"
            assert hint == ".env.minimal"


class TestGetSqliteFilePath:
    def test_sqlite_triple_slash(self):
        settings = SimpleNamespace(database_url="sqlite:///data/spine.db", data_dir="/opt")
        result = _get_sqlite_file_path(settings)
        assert result is not None
        assert "spine.db" in result

    def test_postgres_url_returns_none(self):
        settings = SimpleNamespace(database_url="postgresql://host/db", data_dir="/opt")
        assert _get_sqlite_file_path(settings) is None

    def test_bare_path(self):
        settings = SimpleNamespace(database_url="spine.db", data_dir="/tmp")
        result = _get_sqlite_file_path(settings)
        assert result is not None


class TestGetFileSizeMb:
    def test_none_path(self):
        assert _get_file_size_mb(None) is None

    def test_nonexistent_path(self):
        assert _get_file_size_mb("/nonexistent/path/db.sqlite") is None

    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.db"
        f.write_bytes(b"\x00" * 2048)
        result = _get_file_size_mb(str(f))
        assert result is not None
        assert result > 0


# ── Endpoint tests via TestClient ────────────────────────────

# Build a minimal FastAPI app with the database router


def _make_app():
    """Create a small app with the database router for testing."""
    from fastapi import Depends, FastAPI

    app = FastAPI()

    # We need to override the dependency that provides OpContext
    @app.get("/health-check")
    def hc():
        return {"ok": True}

    app.include_router(router, prefix="/api/v1")
    return app


class TestQueryEndpoint:
    """Test /database/query endpoint logic."""

    def test_select_only(self):
        """Non-SELECT queries are rejected."""
        from fastapi import Depends, FastAPI
        from spine.api.routers.database import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        # Mock the OpContext dependency
        mock_ctx = MagicMock()
        mock_conn = MagicMock()
        mock_ctx.conn = mock_conn

        from spine.api.deps import OpContext

        app.dependency_overrides[OpContext] = lambda: mock_ctx

        client = TestClient(app)

        # DELETE should be rejected
        resp = client.post("/api/v1/database/query", json={"sql": "DELETE FROM core_runs"})
        assert resp.status_code == 400

    def test_dangerous_keywords_rejected(self):
        """Dangerous keywords in query are rejected."""
        from fastapi import FastAPI
        from spine.api.routers.database import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        mock_ctx = MagicMock()
        from spine.api.deps import OpContext

        app.dependency_overrides[OpContext] = lambda: mock_ctx

        client = TestClient(app)

        for kw in ["INSERT", "UPDATE", "DROP", "ALTER"]:
            resp = client.post("/api/v1/database/query", json={"sql": f"SELECT 1; {kw} TABLE x"})
            assert resp.status_code == 400, f"Should reject {kw}"


class TestVacuumEndpoint:
    def test_vacuum_rejects_postgres(self):
        from fastapi import FastAPI
        from spine.api.routers.database import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        mock_ctx = MagicMock()
        from spine.api.deps import OpContext

        app.dependency_overrides[OpContext] = lambda: mock_ctx

        mock_settings = SimpleNamespace(
            database_url="postgresql://localhost/spine",
            data_dir="/tmp",
        )

        client = TestClient(app)
        with patch("spine.api.routers.database.get_settings", return_value=mock_settings):
            resp = client.post("/api/v1/database/vacuum")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success"] is False
        assert "PostgreSQL" in data["message"]


class TestBackupEndpoint:
    def test_backup_rejects_postgres(self):
        from fastapi import FastAPI
        from spine.api.routers.database import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        mock_ctx = MagicMock()
        from spine.api.deps import OpContext

        app.dependency_overrides[OpContext] = lambda: mock_ctx

        mock_settings = SimpleNamespace(
            database_url="postgresql://localhost/spine",
            data_dir="/tmp",
        )

        client = TestClient(app)
        with patch("spine.api.routers.database.get_settings", return_value=mock_settings):
            resp = client.post("/api/v1/database/backup")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success"] is False
        assert "pg_dump" in data["message"]
