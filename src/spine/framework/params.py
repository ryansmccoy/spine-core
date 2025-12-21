"""Parameter validation framework for operations.

Manifesto:
    Operations must validate inputs before executing.  This module
    provides declarative parameter schemas so validation is
    consistent and self-documenting.

Tags:
    spine-core, framework, params, validation, schema

Doc-Types:
    api-reference
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any


@dataclass
class ParamDef:
    """Definition of a operation parameter."""

    name: str
    type: type
    description: str
    required: bool = True
    default: Any = None
    validator: Callable[[Any], bool] | None = None
    error_message: str | None = None

    def validate(self, value: Any) -> tuple[bool, str | None]:
        """
        Validate a parameter value.

        Returns:
            (is_valid, error_message)
        """
        # Type check
        if value is not None and not isinstance(value, self.type):
            # Allow string to be converted to Path
            if self.type == Path and isinstance(value, str):
                value = Path(value)
            else:
                return False, f"Expected type {self.type.__name__}, got {type(value).__name__}"

        # Custom validator
        if self.validator and value is not None:
            try:
                if not self.validator(value):
                    return False, self.error_message or f"Validation failed for {self.name}"
            except Exception as e:
                return False, str(e)

        return True, None


@dataclass
class ValidationResult:
    """Result of parameter validation."""

    valid: bool
    missing_params: list[str] = field(default_factory=list)
    invalid_params: dict[str, str] = field(default_factory=dict)  # param_name -> error_message

    @property
    def has_errors(self) -> bool:
        """Check if validation has any errors."""
        return not self.valid or bool(self.missing_params) or bool(self.invalid_params)

    def get_error_message(self) -> str:
        """Get human-readable error message."""
        messages = []

        if self.missing_params:
            missing_list = ", ".join(self.missing_params)
            messages.append(f"Missing required parameters: {missing_list}")

        if self.invalid_params:
            for param, error in self.invalid_params.items():
                messages.append(f"Invalid parameter '{param}': {error}")

        return ". ".join(messages) if messages else "Validation passed"


class OperationSpec:
    """Operation parameter specification."""

    def __init__(
        self,
        required_params: dict[str, ParamDef] | None = None,
        optional_params: dict[str, ParamDef] | None = None,
        description: str | None = None,
        examples: list[str] | None = None,
        notes: list[str] | None = None,
    ):
        self.required_params = required_params or {}
        self.optional_params = optional_params or {}
        self.description = description
        self.examples = examples or []
        self.notes = notes or []

        # Ensure all required params are marked as required
        for param in self.required_params.values():
            param.required = True

        # Ensure all optional params are marked as not required
        for param in self.optional_params.values():
            param.required = False

    def validate(self, params: dict[str, Any]) -> ValidationResult:
        """
        Validate parameters against this spec.

        Args:
            params: Parameter dictionary to validate

        Returns:
            ValidationResult with validation status and errors
        """
        missing_params = []
        invalid_params = {}

        # Check required params
        for name, param_def in self.required_params.items():
            if name not in params or params[name] is None:
                missing_params.append(name)
            else:
                is_valid, error = param_def.validate(params[name])
                if not is_valid:
                    invalid_params[name] = error

        # Check optional params (if provided)
        for name, param_def in self.optional_params.items():
            if name in params and params[name] is not None:
                is_valid, error = param_def.validate(params[name])
                if not is_valid:
                    invalid_params[name] = error

        # Apply defaults for missing optional params
        for name, param_def in self.optional_params.items():
            if name not in params and param_def.default is not None:
                params[name] = param_def.default

        valid = not missing_params and not invalid_params

        return ValidationResult(valid=valid, missing_params=missing_params, invalid_params=invalid_params)

    def get_help_text(self) -> str:
        """Generate help text for this operation."""
        lines = []

        if self.description:
            lines.append(self.description)
            lines.append("")

        if self.required_params:
            lines.append("Required Parameters:")
            for name, param in self.required_params.items():
                lines.append(f"  {name} ({param.type.__name__}): {param.description}")
            lines.append("")

        if self.optional_params:
            lines.append("Optional Parameters:")
            for name, param in self.optional_params.items():
                default_str = f" [default: {param.default}]" if param.default is not None else ""
                lines.append(f"  {name} ({param.type.__name__}): {param.description}{default_str}")
            lines.append("")

        if self.examples:
            lines.append("Examples:")
            for example in self.examples:
                lines.append(f"  {example}")
            lines.append("")

        if self.notes:
            lines.append("Notes:")
            for note in self.notes:
                lines.append(f"  - {note}")

        return "\n".join(lines)


# =============================================================================
# Built-in Validators
# =============================================================================


def file_exists(path: Path | str) -> bool:
    """Validate that a file exists."""
    return Path(path).exists()


def enum_value(enum_class: type[Enum]) -> Callable[[str], bool]:
    """Create a validator for enum values."""

    def validator(value: str) -> bool:
        try:
            enum_class(value)
            return True
        except (ValueError, KeyError):
            return False

    return validator


def date_format(value: str | date) -> bool:
    """Validate ISO date format (YYYY-MM-DD)."""
    if isinstance(value, date):
        return True

    try:
        date.fromisoformat(value)
        return True
    except (ValueError, AttributeError):
        return False


def positive_int(value: int) -> bool:
    """Validate that an integer is positive."""
    return isinstance(value, int) and value > 0


def non_negative_int(value: int) -> bool:
    """Validate that an integer is non-negative."""
    return isinstance(value, int) and value >= 0
