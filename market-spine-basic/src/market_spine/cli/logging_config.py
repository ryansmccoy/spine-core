"""Logging configuration for CLI."""

import sys
from enum import Enum

from spine.framework.logging import configure_logging as framework_configure_logging


class LogDestination(str, Enum):
    """Log destination options."""

    STDOUT = "stdout"
    STDERR = "stderr"
    FILE = "file"


class LogFormat(str, Enum):
    """Log format options."""

    PRETTY = "pretty"
    JSON = "json"


def configure_cli_logging(
    log_level: str = "INFO",
    log_format: LogFormat = LogFormat.PRETTY,
    log_to: LogDestination = LogDestination.STDOUT,
    log_file: str | None = None,
    quiet: bool = False,
) -> None:
    """
    Configure logging for CLI with proper output channels.
    
    Args:
        log_level: Logging level (INFO, DEBUG, WARNING, ERROR)
        log_format: Format for logs (pretty or json)
        log_to: Destination for logs (stdout, stderr, or file)
        log_file: File path if log_to is FILE
        quiet: If True, suppress most logging output
    """
    # If quiet, set level to WARNING to reduce noise
    if quiet:
        log_level = "WARNING"

    # Configure framework logging
    # For now, we'll use the framework's configure_logging
    # but we could customize the stream based on log_to
    import structlog

    # Determine output stream
    if log_to == LogDestination.STDERR:
        stream = sys.stderr
    else:
        stream = sys.stdout

    # Configure structlog to use the chosen stream
    # This is a simplified version - the framework may need adjustments
    framework_configure_logging()

    # Note: Full implementation would configure the stream here
    # For now, framework_configure_logging handles this
