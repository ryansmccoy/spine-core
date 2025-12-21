"""Spine framework exceptions.

Re-exports from spine.core.errors for backward compatibility.
The canonical error hierarchy lives in spine.core.errors.
"""

from spine.core.errors import (
    BadParamsError,
    OperationError,
    OperationNotFoundError,
    SpineError,
    ValidationError,
)

__all__ = [
    "SpineError",
    "OperationNotFoundError",
    "BadParamsError",
    "ValidationError",
    "OperationError",
]
