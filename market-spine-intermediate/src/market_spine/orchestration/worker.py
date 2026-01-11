"""Worker entry point for running the LocalBackend."""

import signal
import sys

import structlog

from market_spine.config import get_settings
from market_spine.orchestration.backends.local import LocalBackend

logger = structlog.get_logger()


def run_worker() -> None:
    """Run the worker process."""
    settings = get_settings()

    logger.info(
        "worker_starting",
        backend=settings.backend_type,
        poll_interval=settings.worker_poll_interval,
        max_concurrent=settings.worker_max_concurrent,
    )

    backend = LocalBackend()

    # Handle shutdown signals
    def shutdown(signum, frame):
        logger.info("shutdown_signal_received", signal=signum)
        backend.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start backend
    backend.start()

    # Keep main thread alive
    logger.info("worker_running", message="Press Ctrl+C to stop")
    try:
        while True:
            signal.pause()
    except AttributeError:
        # signal.pause() not available on Windows
        import time

        while True:
            time.sleep(1)


if __name__ == "__main__":
    run_worker()
