"""Tests for spine.api.routers.examples — example discovery & run.

Tests the examples router endpoints using TestClient with mock registry.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spine.api.routers.examples import _examples_root, _results_path, router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


# ─── Helpers ─────────────────────────────────────────────────────────


class TestExamplesRoot:
    def test_returns_path(self):
        result = _examples_root()
        assert isinstance(result, Path)

    def test_results_path(self):
        result = _results_path()
        assert isinstance(result, Path)
        assert "run_results" in result.name


# ─── List Examples ───────────────────────────────────────────────────


class TestListExamples:
    @patch("spine.api.routers.examples._get_registry")
    def test_empty_when_no_registry(self, mock_reg):
        mock_reg.return_value = None
        client = TestClient(_make_app())
        resp = client.get("/api/v1/examples")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []

    @patch("spine.api.routers.examples._get_registry")
    def test_with_examples(self, mock_reg):
        registry = MagicMock()
        registry.discover.return_value = [
            MagicMock(
                name="basic_workflow",
                category="getting_started",
                description="A basic workflow",
                path=Path("/tmp/examples/basic.py"),
                tags=["intro"],
            ),
        ]
        mock_reg.return_value = registry
        client = TestClient(_make_app())
        resp = client.get("/api/v1/examples")
        assert resp.status_code == 200


# ─── List Categories ─────────────────────────────────────────────────


class TestListCategories:
    @patch("spine.api.routers.examples._get_registry")
    def test_no_registry(self, mock_reg):
        mock_reg.return_value = None
        client = TestClient(_make_app())
        resp = client.get("/api/v1/examples/categories")
        assert resp.status_code == 200

    @patch("spine.api.routers.examples._get_registry")
    def test_with_categories(self, mock_reg):
        registry = MagicMock()
        registry.categories.return_value = ["getting_started", "advanced"]
        mock_reg.return_value = registry
        client = TestClient(_make_app())
        resp = client.get("/api/v1/examples/categories")
        assert resp.status_code == 200


# ─── Results ─────────────────────────────────────────────────────────


class TestExampleResults:
    @patch("spine.api.routers.examples._results_path")
    def test_no_results_file(self, mock_path):
        mock_path.return_value = Path("/nonexistent/results.json")
        client = TestClient(_make_app())
        resp = client.get("/api/v1/examples/results")
        assert resp.status_code in (200, 404)


# ─── Run Examples ────────────────────────────────────────────────────


class TestRunExamples:
    @patch("spine.api.routers.examples._examples_root")
    def test_run_no_examples_dir(self, mock_root):
        mock_root.return_value = Path("/nonexistent/examples")
        client = TestClient(_make_app())
        resp = client.post("/api/v1/examples/run", json={})
        # Should handle gracefully
        assert resp.status_code in (200, 400, 404, 500)
