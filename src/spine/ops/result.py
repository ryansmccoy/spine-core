"""
Operation result envelope.

Provides :class:`OperationResult` — a typed success/failure envelope that
every operation function returns. Unlike ``spine.core.result.Result`` (a
Rust-style monadic Ok/Err for internal composition), ``OperationResult`` is
designed for API/CLI consumers and carries *warnings*, *elapsed_ms*, and
*metadata* alongside the payload.

This module intentionally does NOT depend on ``spine.core.result`` so the
ops layer stays self-contained.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, TypeVar

from spine.core.errors import ErrorCategory

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class OperationError:
    """Structured error detail for failed operations.

    Attributes:
        code: Machine-readable code (``NOT_FOUND``, ``VALIDATION_FAILED``, …).
        message: Human-readable description of the error.
        category: Optional :class:`ErrorCategory` for routing/alerting.
        details: Extra key/value context (field names, limits, etc.).
        retryable: Whether the caller should retry the operation.
    """

    code: str
    message: str
    category: ErrorCategory | None = None
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False


@dataclass
class OperationResult[T]:
    """Envelope returned by every operation function.

    Factory methods :meth:`ok` and :meth:`fail` should be used instead of
    the constructor directly.

    Attributes:
        success: ``True`` when the operation completed without error.
        data: The typed payload (``None`` on failure).
        error: Structured error (``None`` on success).
        warnings: Non-fatal messages collected during the operation.
        elapsed_ms: Wall-clock time the operation took.
        metadata: Additional key/value pairs for debugging or tracing.
    """

    success: bool
    data: T | None = None
    error: OperationError | None = None
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Factory helpers
    # ------------------------------------------------------------------ #

    @classmethod
    def ok(
        cls,
        data: T,
        *,
        warnings: list[str] | None = None,
        elapsed_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> OperationResult[T]:
        """Create a successful result."""
        return cls(
            success=True,
            data=data,
            warnings=warnings or [],
            elapsed_ms=elapsed_ms,
            metadata=metadata or {},
        )

    @classmethod
    def fail(
        cls,
        code: str,
        message: str,
        *,
        category: ErrorCategory | None = None,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        warnings: list[str] | None = None,
        elapsed_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> OperationResult[T]:
        """Create a failed result."""
        return cls(
            success=False,
            error=OperationError(
                code=code,
                message=message,
                category=category,
                details=details or {},
                retryable=retryable,
            ),
            warnings=warnings or [],
            elapsed_ms=elapsed_ms,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (for JSON responses)."""
        d: dict[str, Any] = {"success": self.success}
        if self.data is not None:
            d["data"] = self.data
        if self.error is not None:
            d["error"] = {
                "code": self.error.code,
                "message": self.error.message,
                "retryable": self.error.retryable,
            }
            if self.error.details:
                d["error"]["details"] = self.error.details
        if self.warnings:
            d["warnings"] = self.warnings
        if self.elapsed_ms:
            d["elapsed_ms"] = round(self.elapsed_ms, 2)
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass
class PagedResult(OperationResult[list[T]]):
    """Paginated result for list operations.

    Extends :class:`OperationResult` with pagination info.
    ``has_more`` is computed automatically from *total*, *offset*, and *limit*.

    Attributes:
        total: Total number of matching items (before pagination).
        limit: Maximum items per page.
        offset: Current page offset.
        has_more: Whether more pages exist beyond this one.
    """

    total: int = 0
    limit: int = 50
    offset: int = 0
    has_more: bool = False

    @classmethod
    def from_items(
        cls,
        items: list[T],
        total: int,
        *,
        limit: int = 50,
        offset: int = 0,
        warnings: list[str] | None = None,
        elapsed_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> PagedResult[T]:
        """Convenience factory that auto-computes ``has_more``."""
        return cls(
            success=True,
            data=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
            warnings=warnings or [],
            elapsed_ms=elapsed_ms,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["total"] = self.total
        d["limit"] = self.limit
        d["offset"] = self.offset
        d["has_more"] = self.has_more
        return d


# ------------------------------------------------------------------ #
# Timing helper
# ------------------------------------------------------------------ #


class _Timer:
    """Minimal stopwatch for timing operations."""

    __slots__ = ("_start",)

    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000


def start_timer() -> _Timer:
    """Return a lightweight timer.  Use ``timer.elapsed_ms`` when done."""
    return _Timer()
