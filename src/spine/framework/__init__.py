"""
Spine Framework - Application infrastructure for data operations.

This module provides:
- Operation base classes and registration
- Structured logging with context
- Execution dispatching
- Operation runner
- Source protocol and adapters (NEW)
- Alerting framework (NEW)

All components are tier-agnostic and work with any backend.
"""

from spine.framework.operations import Operation, OperationResult, OperationStatus
from spine.framework.registry import clear_registry, get_operation, list_operations, register_operation
from spine.framework.runner import OperationRunner, get_runner

# New modules - imported lazily to avoid circular imports
# Use: from spine.framework.sources import FileSource, source_registry
# Use: from spine.framework.alerts import SlackChannel, alert_registry

__all__ = [
    # Operations
    "Operation",
    "OperationResult",
    "OperationStatus",
    # Registry
    "register_operation",
    "get_operation",
    "list_operations",
    "clear_registry",
    # Runner
    "OperationRunner",
    "get_runner",
]
