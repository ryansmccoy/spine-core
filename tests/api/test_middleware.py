"""
Tests for API middleware — error mapping, request ID, timing.
"""

from __future__ import annotations

import pytest

from spine.api.middleware.errors import (
    ERROR_CODE_TO_STATUS,
    problem_response,
    status_for_error_code,
)


class TestErrorCodeMapping:
    def test_known_codes(self):
        assert status_for_error_code("NOT_FOUND") == 404
        assert status_for_error_code("CONFLICT") == 409
        assert status_for_error_code("VALIDATION_FAILED") == 400
        assert status_for_error_code("NOT_CANCELLABLE") == 409
        assert status_for_error_code("LOCKED") == 423
        assert status_for_error_code("QUOTA_EXCEEDED") == 429
        assert status_for_error_code("TRANSIENT") == 503
        assert status_for_error_code("INTERNAL") == 500

    def test_unknown_code_defaults_to_500(self):
        assert status_for_error_code("UNKNOWN_ERROR") == 500
        assert status_for_error_code("") == 500

    def test_mapping_completeness(self):
        """Every value in the map should be a valid HTTP status."""
        for code, status in ERROR_CODE_TO_STATUS.items():
            assert 400 <= status <= 599, f"{code} -> {status}"


class TestProblemResponse:
    def test_basic(self):
        resp = problem_response(status=404, title="Not Found", detail="missing")
        assert resp.status_code == 404

    def test_body_structure(self):
        import json
        resp = problem_response(status=400, title="Bad Request")
        body = json.loads(resp.body)
        assert body["status"] == 400
        assert body["title"] == "Bad Request"
        assert "type" in body

    def test_with_errors(self):
        import json
        resp = problem_response(
            status=400,
            title="Validation",
            errors=[{"code": "REQUIRED", "message": "name is required"}],
        )
        body = json.loads(resp.body)
        assert len(body["errors"]) == 1
