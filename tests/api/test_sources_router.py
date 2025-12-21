"""Tests for spine.api.routers.sources — Pydantic schema unit tests.

Tests the Pydantic request/response schemas and basic endpoint routing.
Avoids deep router integration (which requires real ops wiring) by
focusing on schema validation and model construction.
"""

from __future__ import annotations

import pytest

from spine.api.routers.sources import (
    DatabaseConnectionCreateRequest,
    DatabaseConnectionSchema,
    SourceCacheSchema,
    SourceCreateRequest,
    SourceDetailSchema,
    SourceFetchSchema,
    SourceSchema,
)


class TestSourceSchema:
    def test_defaults(self):
        s = SourceSchema(id="s-1", name="test", source_type="http")
        assert s.enabled is True
        assert s.domain is None

    def test_all_fields(self):
        s = SourceSchema(
            id="s-1", name="test", source_type="http",
            domain="finance", enabled=False, created_at="2024-01-01",
        )
        assert s.domain == "finance"
        assert s.enabled is False


class TestSourceDetailSchema:
    def test_defaults(self):
        d = SourceDetailSchema(id="s-1", name="test", source_type="http")
        assert d.config == {}
        assert d.enabled is True

    def test_full(self):
        d = SourceDetailSchema(
            id="s-1", name="test", source_type="http",
            config={"url": "http://example.com"}, domain="finance",
            enabled=True, created_at="2024-01-01", updated_at="2024-01-02",
        )
        assert d.config["url"] == "http://example.com"


class TestSourceCreateRequest:
    def test_required_fields(self):
        r = SourceCreateRequest(name="sec-edgar", source_type="http")
        assert r.enabled is True
        assert r.domain is None

    def test_with_config(self):
        r = SourceCreateRequest(
            name="sec-edgar", source_type="http",
            config={"url": "https://example.com"}, domain="sec",
        )
        assert r.config["url"] == "https://example.com"


class TestSourceFetchSchema:
    def test_minimal(self):
        f = SourceFetchSchema(
            id="f-1", source_name="test", source_type="http",
            source_locator="https://example.com", status="completed",
        )
        assert f.record_count is None
        assert f.source_id is None

    def test_full(self):
        f = SourceFetchSchema(
            id="f-1", source_id="s-1", source_name="test",
            source_type="http", source_locator="https://example.com",
            status="completed", record_count=100, byte_count=5000,
            started_at="2024-01-01", duration_ms=500,
        )
        assert f.record_count == 100
        assert f.byte_count == 5000


class TestSourceCacheSchema:
    def test_construction(self):
        c = SourceCacheSchema(
            cache_key="k-1", source_type="http",
            source_locator="https://example.com",
            content_hash="abc123", content_size=1024,
        )
        assert c.content_size == 1024
        assert c.expires_at is None


class TestDatabaseConnectionSchema:
    def test_defaults(self):
        d = DatabaseConnectionSchema(
            id="c-1", name="local-pg", dialect="postgresql", database="spine",
        )
        assert d.enabled is True
        assert d.host is None

    def test_full(self):
        d = DatabaseConnectionSchema(
            id="c-1", name="local-pg", dialect="postgresql",
            host="localhost", port=5432, database="spine",
            enabled=True, last_error=None,
        )
        assert d.port == 5432


class TestDatabaseConnectionCreateRequest:
    def test_required(self):
        r = DatabaseConnectionCreateRequest(
            name="local-pg", dialect="postgresql", database="spine",
        )
        assert r.enabled is True

    def test_with_credentials(self):
        r = DatabaseConnectionCreateRequest(
            name="remote-pg", dialect="postgresql",
            host="db.example.com", port=5432, database="spine",
            username="admin", password="secret",
        )
        assert r.host == "db.example.com"
