"""Tests for parameter validation framework."""

import pytest

from spine.framework.exceptions import BadParamsError
from spine.framework.params import (
    ParamDef,
    PipelineSpec,
    ValidationResult,
    date_format,
    enum_value,
    file_exists,
    non_negative_int,
    positive_int,
)


class TestParamDef:
    """Tests for ParamDef dataclass."""

    def test_param_def_creation(self):
        """Test creating a ParamDef."""
        param = ParamDef(
            name="test_param",
            type=str,
            description="A test parameter",
        )
        assert param.name == "test_param"
        assert param.type == str
        assert param.description == "A test parameter"
        assert param.required is True  # default
        assert param.default is None

    def test_param_def_with_defaults(self):
        """Test ParamDef with default values."""
        param = ParamDef(
            name="optional_param",
            type=bool,
            description="Optional boolean",
            required=False,
            default=False,
        )
        assert param.required is False
        assert param.default is False

    def test_param_def_with_validator(self):
        """Test ParamDef with a validator function."""
        param = ParamDef(
            name="positive_number",
            type=int,
            description="Must be positive",
            validator=positive_int,
            error_message="Value must be positive",
        )
        assert param.validator is not None
        assert param.error_message == "Value must be positive"


class TestValidators:
    """Tests for built-in validators."""

    def test_positive_int_valid(self):
        """Test positive_int with valid values."""
        assert positive_int(1) is True
        assert positive_int(100) is True
        # Note: positive_int expects int, not string

    def test_positive_int_invalid(self):
        """Test positive_int with invalid values."""
        assert positive_int(0) is False
        assert positive_int(-1) is False

    def test_non_negative_int_valid(self):
        """Test non_negative_int with valid values."""
        assert non_negative_int(0) is True
        assert non_negative_int(1) is True
        assert non_negative_int(10) is True

    def test_non_negative_int_invalid(self):
        """Test non_negative_int with invalid values."""
        assert non_negative_int(-1) is False

    def test_date_format_valid(self):
        """Test date_format with valid dates."""
        assert date_format("2025-01-03") is True
        assert date_format("2024-12-31") is True

    def test_date_format_invalid(self):
        """Test date_format with invalid dates."""
        assert date_format("01-03-2025") is False
        assert date_format("2025/01/03") is False
        assert date_format("not-a-date") is False
        assert date_format("2025-13-01") is False  # invalid month


class TestEnumValidator:
    """Tests for enum_value validator factory."""

    def test_enum_value_valid(self):
        """Test enum_value with valid enum members."""
        from enum import Enum

        class Color(Enum):
            RED = "red"
            BLUE = "blue"

        validator = enum_value(Color)
        assert validator("red") is True
        assert validator("blue") is True
        # Note: enum_value uses Enum(value), so must match exactly

    def test_enum_value_invalid(self):
        """Test enum_value with invalid values."""
        from enum import Enum

        class Color(Enum):
            RED = "red"
            BLUE = "blue"

        validator = enum_value(Color)
        assert validator("green") is False
        assert validator("") is False
        assert validator("RED") is False  # case-sensitive


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """Test creating a valid result."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.missing_params == []
        assert result.invalid_params == {}  # Dict, not list

    def test_invalid_result_missing(self):
        """Test result with missing params."""
        result = ValidationResult(
            valid=False,
            missing_params=["file_path", "tier"],
        )
        assert result.valid is False
        assert "file_path" in result.missing_params
        assert "tier" in result.missing_params

    def test_get_error_message(self):
        """Test error message generation."""
        result = ValidationResult(
            valid=False,
            missing_params=["param1"],
            invalid_params={"param2": "Invalid value"},  # Dict with error message
        )
        message = result.get_error_message()
        assert "param1" in message
        assert "param2" in message


class TestPipelineSpec:
    """Tests for PipelineSpec class."""

    def test_spec_creation(self):
        """Test creating a PipelineSpec."""
        spec = PipelineSpec(
            required_params={
                "file_path": ParamDef(
                    name="file_path",
                    type=str,
                    description="Path to file",
                ),
            },
            optional_params={
                "force": ParamDef(
                    name="force",
                    type=bool,
                    description="Force overwrite",
                    required=False,
                    default=False,
                ),
            },
            description="Test pipeline",
            examples=["spine run test -p file_path=data.csv"],
        )
        assert "file_path" in spec.required_params
        assert "force" in spec.optional_params
        assert spec.description == "Test pipeline"

    def test_validate_valid_params(self):
        """Test validation with valid params."""
        spec = PipelineSpec(
            required_params={
                "week_ending": ParamDef(
                    name="week_ending",
                    type=str,
                    description="Week ending date",
                    validator=date_format,
                ),
            },
        )
        result = spec.validate({"week_ending": "2025-01-03"})
        assert result.valid is True

    def test_validate_missing_required(self):
        """Test validation with missing required params."""
        spec = PipelineSpec(
            required_params={
                "file_path": ParamDef(
                    name="file_path",
                    type=str,
                    description="Path to file",
                ),
                "tier": ParamDef(
                    name="tier",
                    type=str,
                    description="Tier value",
                ),
            },
        )
        result = spec.validate({"file_path": "test.csv"})
        assert result.valid is False
        assert "tier" in result.missing_params

    def test_validate_invalid_value(self):
        """Test validation with invalid param value."""
        spec = PipelineSpec(
            required_params={
                "count": ParamDef(
                    name="count",
                    type=int,
                    description="Must be positive",
                    validator=positive_int,
                ),
            },
        )
        result = spec.validate({"count": -1})
        assert result.valid is False
        assert "count" in result.invalid_params

    def test_get_help_text(self):
        """Test help text generation."""
        spec = PipelineSpec(
            required_params={
                "file_path": ParamDef(
                    name="file_path",
                    type=str,
                    description="Path to the input file",
                ),
            },
            optional_params={
                "force": ParamDef(
                    name="force",
                    type=bool,
                    description="Force overwrite",
                    required=False,
                    default=False,
                ),
            },
            examples=["spine run test -p file_path=data.csv"],
            notes=["Use force=True to overwrite existing data"],
        )
        help_text = spec.get_help_text()
        assert "file_path" in help_text
        assert "force" in help_text
        assert "Required" in help_text
        assert "Optional" in help_text


class TestBadParamsError:
    """Tests for BadParamsError exception."""

    def test_error_with_missing_params(self):
        """Test BadParamsError with missing params."""
        error = BadParamsError(
            "Missing required parameters",
            missing_params=["file_path", "tier"],
        )
        assert "file_path" in error.missing_params
        assert "tier" in error.missing_params
        assert error.invalid_params == []

    def test_error_with_invalid_params(self):
        """Test BadParamsError with invalid params."""
        error = BadParamsError(
            "Invalid parameters",
            invalid_params=["count"],
        )
        assert error.missing_params == []
        assert "count" in error.invalid_params

    def test_error_str(self):
        """Test error string representation."""
        error = BadParamsError("Test error message")
        assert str(error) == "Test error message"
