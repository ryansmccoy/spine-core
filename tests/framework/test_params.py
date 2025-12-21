"""Tests for ``spine.framework.params`` — operation parameter validation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from spine.framework.params import (
    ParamDef,
    OperationSpec,
    ValidationResult,
    date_format,
    non_negative_int,
    positive_int,
)


class TestParamDef:
    def test_basic_string_param(self):
        p = ParamDef(name="ticker", type=str, description="Stock ticker")
        valid, msg = p.validate("AAPL")
        assert valid is True
        assert msg is None

    def test_type_check_fails(self):
        p = ParamDef(name="count", type=int, description="Count")
        valid, msg = p.validate("not-an-int")
        assert valid is False
        assert msg is not None

    def test_custom_validator_passes(self):
        p = ParamDef(
            name="count",
            type=int,
            description="Count",
            validator=lambda x: x > 0,
        )
        valid, msg = p.validate(5)
        assert valid is True

    def test_custom_validator_fails(self):
        p = ParamDef(
            name="count",
            type=int,
            description="Count",
            validator=lambda x: x > 0,
            error_message="must be positive",
        )
        valid, msg = p.validate(-1)
        assert valid is False
        assert "positive" in msg

    def test_none_for_optional(self):
        p = ParamDef(name="opt", type=str, description="Optional", required=False)
        # None should be valid for optional params
        valid, msg = p.validate(None)
        assert valid is True


class TestValidationResult:
    def test_valid_result(self):
        vr = ValidationResult(valid=True, missing_params=[], invalid_params={})
        assert vr.has_errors is False

    def test_invalid_with_missing(self):
        vr = ValidationResult(valid=False, missing_params=["x"], invalid_params={})
        assert vr.has_errors is True
        msg = vr.get_error_message()
        assert "x" in msg

    def test_invalid_with_invalid_params(self):
        vr = ValidationResult(
            valid=False,
            missing_params=[],
            invalid_params={"count": "must be positive"},
        )
        assert vr.has_errors is True
        msg = vr.get_error_message()
        assert "count" in msg


class TestOperationSpec:
    def test_validate_all_required_present(self):
        spec = OperationSpec(
            required_params={
                "ticker": ParamDef(name="ticker", type=str, description="Ticker"),
            },
        )
        result = spec.validate({"ticker": "AAPL"})
        assert result.valid is True

    def test_validate_missing_required(self):
        spec = OperationSpec(
            required_params={
                "ticker": ParamDef(name="ticker", type=str, description="Ticker"),
            },
        )
        result = spec.validate({})
        assert result.valid is False
        assert "ticker" in result.missing_params

    def test_validate_with_defaults(self):
        spec = OperationSpec(
            required_params={
                "ticker": ParamDef(name="ticker", type=str, description="Ticker"),
            },
            optional_params={
                "limit": ParamDef(
                    name="limit",
                    type=int,
                    description="Limit",
                    required=False,
                    default=50,
                ),
            },
        )
        result = spec.validate({"ticker": "AAPL"})
        assert result.valid is True

    def test_get_help_text(self):
        spec = OperationSpec(
            required_params={
                "ticker": ParamDef(name="ticker", type=str, description="Stock ticker"),
            },
            optional_params={
                "limit": ParamDef(name="limit", type=int, description="Row limit", required=False, default=50),
            },
            description="Fetch stock data",
        )
        help_text = spec.get_help_text()
        assert "ticker" in help_text
        assert "limit" in help_text


class TestBuiltinValidators:
    def test_positive_int_valid(self):
        assert positive_int(1) is True
        assert positive_int(100) is True

    def test_positive_int_invalid(self):
        assert positive_int(0) is False
        assert positive_int(-1) is False

    def test_non_negative_int_valid(self):
        assert non_negative_int(0) is True
        assert non_negative_int(10) is True

    def test_non_negative_int_invalid(self):
        assert non_negative_int(-1) is False

    def test_date_format_valid_string(self):
        assert date_format("2024-01-15") is True

    def test_date_format_valid_date(self):
        assert date_format(date(2024, 1, 15)) is True

    def test_date_format_invalid(self):
        assert date_format("not-a-date") is False
        assert date_format("01-15-2024") is False
