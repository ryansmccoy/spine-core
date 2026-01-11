"""
Shared data models for commands and services.

These models are used by both CLI and API adapters. They define
the contract for command inputs/outputs and error handling.

Design principles:
    1. Use dataclasses for simplicity (Pydantic for API response models)
    2. Commands return Result objects with optional error
    3. Error details are structured, not just strings
    4. Reserved fields for future tier evolution (nullable)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """
    Enumerated error codes for structured error handling.

    Clients should switch on these codes for programmatic handling.
    New codes may be added in future versions.
    """

    # Pipeline errors
    PIPELINE_NOT_FOUND = "PIPELINE_NOT_FOUND"
    INVALID_PARAMS = "INVALID_PARAMS"
    EXECUTION_FAILED = "EXECUTION_FAILED"

    # Validation errors
    INVALID_TIER = "INVALID_TIER"
    INVALID_DATE = "INVALID_DATE"
    MISSING_REQUIRED = "MISSING_REQUIRED"

    # System errors
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    # Tier capability errors
    FEATURE_NOT_SUPPORTED = "FEATURE_NOT_SUPPORTED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass
class CommandError:
    """
    Structured error from a command.

    Attributes:
        code: Machine-readable error code (stable, switch on this)
        message: Human-readable error message (can change)
        details: Additional context for debugging (schema stable per code)
    """

    code: ErrorCode
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    """
    Base result class for commands.

    All command results should inherit from this and include
    the success/error fields. This allows uniform error handling
    across CLI and API.
    """

    success: bool = True
    error: CommandError | None = None

    def failed(self) -> bool:
        """Check if the result indicates failure."""
        return not self.success


# =============================================================================
# Pipeline-related models
# =============================================================================


@dataclass
class PipelineSummary:
    """Summary of a pipeline for list operations."""

    name: str
    description: str


@dataclass
class ParameterDef:
    """Definition of a pipeline parameter."""

    name: str
    type: str
    description: str
    default: Any = None
    required: bool = True
    choices: list[str] | None = None


@dataclass
class PipelineDetail:
    """Full details of a pipeline."""

    name: str
    description: str
    required_params: list[ParameterDef]
    optional_params: list[ParameterDef]
    is_ingest: bool


# =============================================================================
# Execution-related models
# =============================================================================


class ExecutionStatus(str, Enum):
    """Status of a pipeline execution."""

    PENDING = "pending"  # Reserved for async (Intermediate tier)
    RUNNING = "running"  # Reserved for async (Intermediate tier)
    COMPLETED = "completed"
    FAILED = "failed"
    DRY_RUN = "dry_run"


@dataclass
class IngestResolution:
    """
    How an ingest file path was resolved.

    For ingest pipelines, this explains whether the file path
    was provided explicitly or derived from parameters.
    """

    source_type: str  # "explicit" | "derived"
    file_path: str
    derivation_logic: str | None = None  # Explanation if derived


@dataclass
class ExecutionMetrics:
    """Metrics from a pipeline execution."""

    rows_processed: int | None = None
    duration_seconds: float | None = None
    capture_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Query-related models
# =============================================================================


@dataclass
class WeekInfo:
    """Information about an available week of data."""

    week_ending: str
    symbol_count: int


@dataclass
class SymbolInfo:
    """Information about a symbol's trading activity."""

    symbol: str
    volume: int
    avg_price: float | None


@dataclass
class SymbolWeekData:
    """Trading data for a symbol in a specific week."""

    week_ending: str
    total_shares: int
    total_trades: int
    average_price: float | None


# =============================================================================
# Health and capability models
# =============================================================================


@dataclass
class HealthCheck:
    """Result of a single health check."""

    name: str
    status: str  # "ok" | "error" | "warning"
    message: str


@dataclass
class Capabilities:
    """
    Tier capabilities for API introspection.

    Allows clients to discover what features are available
    in the current tier without hard-coding tier detection.
    """

    tier: str
    version: str
    sync_execution: bool = True
    async_execution: bool = False
    execution_history: bool = False
    authentication: bool = False
    scheduling: bool = False
    rate_limiting: bool = False
