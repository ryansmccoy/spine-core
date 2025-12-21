"""Tests for framework params — ParamDef validation, OperationSpec, and validators.

Pure logic with zero external dependencies.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from spine.framework.params import (
    OperationSpec,
    ParamDef,
    ValidationResult,
    date_format,
    non_negative_int,
    positive_int,
)


# ── ParamDef ─────────────────────────────────────────────────


class TestParamDef:
    def test_basic_required_param(self):
        p = ParamDef("name", str, "User name", required=True)
        ok, err = p.validate("Alice")
        assert ok is True
        assert err is None

    def test_type_mismatch(self):
        p = ParamDef("age", int, "Age", required=True)
        ok, err = p.validate("not-a-number")
        assert ok is False
        assert err is not None

    def test_none_for_required_passes_at_param_level(self):
        """ParamDef.validate(None) returns True — missing check is at OperationSpec level."""
        p = ParamDef("name", str, "Name", required=True)
        ok, err = p.validate(None)
        assert ok is True

    def test_none_for_optional(self):
        p = ParamDef("tag", str, "Optional tag", required=False)
        ok, err = p.validate(None)
        assert ok is True

    def test_path_coercion(self):
        p = ParamDef("path", Path, "File path", required=True)
        ok, err = p.validate("/tmp/test.txt")
        assert ok is True

    def test_custom_validator_pass(self):
        p = ParamDef("x", int, "Positive", required=True,
                      validator=lambda v: v > 0)
        ok, err = p.validate(5)
        assert ok is True

    def test_custom_validator_fail(self):
        p = ParamDef("x", int, "Positive", required=True,
                      validator=lambda v: v > 0)
        ok, err = p.validate(-1)
        assert ok is False

    def test_custom_validator_exception(self):
        def bad_validator(v):
            raise ValueError("boom")

        p = ParamDef("x", str, "Test", required=True,
                      validator=bad_validator)
        ok, err = p.validate("test")
        assert ok is False
        assert "boom" in err


# ── ValidationResult ─────────────────────────────────────────


class TestValidationResult:
    def test_no_errors(self):
        vr = ValidationResult(valid=True)
        assert vr.has_errors is False

    def test_missing_error(self):
        vr = ValidationResult(valid=False, missing_params=["name"])
        assert vr.has_errors is True
        msg = vr.get_error_message()
        assert "name" in msg

    def test_invalid_error(self):
        vr = ValidationResult(valid=False, invalid_params={"age": "must be int"})
        assert vr.has_errors is True
        msg = vr.get_error_message()
        assert "age" in msg

    def test_both_errors(self):
        vr = ValidationResult(valid=False, missing_params=["name"], invalid_params={"age": "bad"})
        assert vr.has_errors is True
        msg = vr.get_error_message()
        assert "name" in msg
        assert "age" in msg

    def test_get_error_message_clean(self):
        vr = ValidationResult(valid=True)
        assert vr.get_error_message() == "Validation passed"


# ── OperationSpec ────────────────────────────────────────────


class TestOperationSpec:
    def _make_spec(self):
        return OperationSpec(
            description="Test operation",
            required_params={
                "name": ParamDef("name", str, "Name"),
            },
            optional_params={
                "count": ParamDef("count", int, "Count", default=10),
            },
        )

    def test_validate_all_present(self):
        spec = self._make_spec()
        result = spec.validate({"name": "Alice", "count": 5})
        assert result.has_errors is False

    def test_validate_optional_default(self):
        spec = self._make_spec()
        params = {"name": "Alice"}
        result = spec.validate(params)
        assert result.has_errors is False
        assert params["count"] == 10  # Default applied in-place

    def test_validate_missing_required(self):
        spec = self._make_spec()
        result = spec.validate({})
        assert result.has_errors is True
        assert "name" in result.missing_params

    def test_validate_invalid_type(self):
        spec = self._make_spec()
        result = spec.validate({"name": "Alice", "count": "not-int"})
        assert result.has_errors is True
        assert "count" in result.invalid_params

    def test_get_help_text(self):
        spec = self._make_spec()
        help_text = spec.get_help_text()
        assert "Test operation" in help_text
        assert "name" in help_text
        assert "count" in help_text

    def test_examples_and_notes(self):
        spec = OperationSpec(
            description="Op",
            examples=["do_it('foo')"],
            notes=["Runs slowly"],
        )
        txt = spec.get_help_text()
        assert "do_it" in txt
        assert "Runs slowly" in txt


# ── Built-in validators ─────────────────────────────────────


class TestBuiltinValidators:
    def test_date_format_valid_string(self):
        assert date_format("2024-01-15") is True

    def test_date_format_valid_date_obj(self):
        assert date_format(date(2024, 1, 15)) is True

    def test_date_format_invalid(self):
        assert date_format("not-a-date") is False

    def test_positive_int_valid(self):
        assert positive_int(5) is True

    def test_positive_int_zero(self):
        assert positive_int(0) is False

    def test_positive_int_negative(self):
        assert positive_int(-1) is False

    def test_non_negative_int_valid(self):
        assert non_negative_int(0) is True

    def test_non_negative_int_positive(self):
        assert non_negative_int(5) is True

    def test_non_negative_int_negative(self):
        assert non_negative_int(-1) is False
